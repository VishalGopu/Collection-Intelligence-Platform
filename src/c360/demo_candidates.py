"""Select reproducible, linked C360 demo customers without protected fields."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def sql_path(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def find_candidates(data_dir: Path, output_dir: Path, limit: int = 5) -> list[dict]:
    data = data_dir.resolve() / "data"
    output = output_dir.resolve()
    con = duckdb.connect(":memory:")
    try:
        con.execute("SET memory_limit = '4GB'")
        rows = con.execute(f"""
            WITH dup AS (
              SELECT golden_customer_id, len(crm_customer_ids) AS crm_record_count,
                     hardship_flag
              FROM read_parquet({sql_path(output / 'golden_customers.parquet')})
              WHERE len(crm_customer_ids) > 1
            ), linked_cases AS (
              SELECT d.golden_customer_id, d.crm_record_count, d.hardship_flag,
                     c.case_id, c.case_status
              FROM dup d
              JOIN read_parquet({sql_path(output / 'identity_crosswalk.parquet')}) x
                ON x.golden_customer_id = d.golden_customer_id
               AND x.source_system = 'collections' AND x.link_status = 'linked'
              JOIN read_csv({sql_path(data / 'collections_cases.csv')}, header=true, all_varchar=true) c
                ON c.coll_customer_ref = x.source_customer_id
            ), broken AS (
              SELECT p.case_id, count(*) AS broken_promises
              FROM read_csv({sql_path(data / 'promises_to_pay.csv')}, header=true, all_varchar=true) p
              WHERE p.ptp_status = 'broken'
              GROUP BY p.case_id
            ), notes AS (
              SELECT n.case_id, count(*) AS note_count
              FROM read_csv({sql_path(data / 'agent_notes.csv')}, header=true, all_varchar=true) n
              GROUP BY n.case_id
            ), transcripts AS (
              SELECT t.case_id, count(*) AS transcript_count
              FROM read_csv({sql_path(data / 'call_transcripts.csv')}, header=true, all_varchar=true) t
              GROUP BY t.case_id
            )
            SELECT l.golden_customer_id, max(l.crm_record_count) AS crm_record_count,
                   count(DISTINCT l.case_id) AS linked_cases,
                   sum(coalesce(b.broken_promises, 0)) AS broken_promises,
                   sum(coalesce(n.note_count, 0)) AS notes,
                   sum(coalesce(t.transcript_count, 0)) AS transcripts,
                   bool_or(l.hardship_flag) AS hardship_flag,
                   bool_or(l.case_status = 'open') AS has_open_case
            FROM linked_cases l
            JOIN broken b ON b.case_id = l.case_id
            LEFT JOIN notes n ON n.case_id = l.case_id
            LEFT JOIN transcripts t ON t.case_id = l.case_id
            GROUP BY l.golden_customer_id
            HAVING sum(coalesce(n.note_count, 0)) + sum(coalesce(t.transcript_count, 0)) > 0
            ORDER BY hardship_flag DESC, transcripts DESC, broken_promises DESC,
                     notes DESC, l.golden_customer_id
            LIMIT ?
        """, [limit]).fetchall()
    finally:
        con.close()
    return [dict(zip(("golden_customer_id", "crm_record_count", "linked_cases",
                      "broken_promises", "notes", "transcripts", "hardship_flag",
                      "has_open_case"), row)) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("maple_data/maple_collections_release"))
    parser.add_argument("--output-dir", type=Path, default=Path("local_artifacts/c360"))
    args = parser.parse_args()
    print(json.dumps(find_candidates(args.data_dir, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
