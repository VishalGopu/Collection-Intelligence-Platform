"""Read-only portfolio summary for the manager dashboard."""

from __future__ import annotations

from pathlib import Path

import duckdb

from app.customer import C360, DATASET, _path


def portfolio_snapshot(dataset_root: Path = DATASET, c360_root: Path = C360) -> dict:
    data = Path(dataset_root) / "data"
    cases = data / "collections_cases.csv"
    promises = data / "promises_to_pay.csv"
    gold = Path(c360_root) / "golden_customers.parquet"
    for source in (cases, promises, gold):
        if not source.is_file():
            raise FileNotFoundError(source)

    con = duckdb.connect(":memory:")
    try:
        con.execute("SET memory_limit='1GB'")
        con.execute("SET threads=2")
        con.execute(f"CREATE VIEW cases AS SELECT case_status, case_open_date, "
                    "try_cast(current_dpd AS INTEGER) AS dpd, "
                    "try_cast(total_overdue AS DECIMAL(18,2)) AS overdue_cad, queue "
                    f"FROM read_csv({_path(cases)}, header=true, all_varchar=true)")
        totals = con.execute("""SELECT count(*) FILTER (WHERE case_status='open') AS open_cases,
            coalesce(sum(overdue_cad) FILTER (WHERE case_status='open'), 0) AS overdue_cad
            FROM cases""").fetchone()
        bucket_rows = con.execute("""SELECT CASE
                WHEN dpd IS NULL THEN 'Unknown'
                WHEN dpd < 30 THEN '0–29 days'
                WHEN dpd < 60 THEN '30–59 days'
                WHEN dpd < 90 THEN '60–89 days'
                ELSE '90+ days' END AS bucket, count(*) AS cases
            FROM cases WHERE case_status='open' GROUP BY 1""").fetchall()
        queue_rows = con.execute("""SELECT queue, count(*) AS open_cases,
            round(avg(dpd), 1) AS avg_dpd,
            round(sum(overdue_cad), 2) AS overdue_cad
            FROM cases WHERE case_status='open' GROUP BY queue
            ORDER BY open_cases DESC, queue""").fetchall()
        weekly_rows = con.execute("""SELECT strftime(date_trunc('week', try_cast(case_open_date AS DATE)),
                '%d %b') AS week, count(*) AS new_cases
            FROM cases WHERE try_cast(case_open_date AS DATE) >= DATE '2026-08-10'
                AND try_cast(case_open_date AS DATE) < DATE '2026-09-29'
            GROUP BY date_trunc('week', try_cast(case_open_date AS DATE))
            ORDER BY date_trunc('week', try_cast(case_open_date AS DATE))""").fetchall()
        open_promises = con.execute(f"SELECT count(*) FROM read_csv({_path(promises)}, "
                                    "header=true, all_varchar=true) WHERE ptp_status='open'").fetchone()[0]
        linked_customers, snapshot_date = con.execute(
            f"SELECT count(*), max(as_of_date) FROM read_parquet({_path(gold)})"
        ).fetchone()
        return {
            "open_cases": totals[0], "overdue_cad": float(totals[1]),
            "open_promises": open_promises, "linked_customers": linked_customers,
            "snapshot_date": str(snapshot_date),
            "buckets": [{"bucket": label, "cases": count} for label, count in bucket_rows],
            "queues": [{"queue": queue, "open_cases": count, "avg_dpd": avg_dpd,
                        "overdue_cad": float(overdue or 0)}
                       for queue, count, avg_dpd, overdue in queue_rows],
            "weekly": [{"week": week, "new_cases": count} for week, count in weekly_rows],
        }
    finally:
        con.close()
