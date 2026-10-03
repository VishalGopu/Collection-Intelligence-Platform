"""Build a conservative golden customer view from the Maple release.

Run from the repository root with ``.venv/Scripts/python src/c360/build.py``.
The source release is read-only; all generated files go to local_artifacts/c360.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb

from quality import validate_publication


SNAPSHOT_DATE = "2026-09-28"


def sql_path(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("maple_data/maple_collections_release"),
        help="Extracted Maple release directory",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("local_artifacts/c360")
    )
    args = parser.parse_args()
    data = args.data_dir.resolve()
    output = args.output_dir.resolve()
    if not (data / "data/customers.csv").is_file():
        parser.error(f"Release not found at {data}; see docs/DATASET_DOWNLOAD.md")
    output.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(output / "work.duckdb"))
    con.execute("SET memory_limit = '4GB'")
    con.execute(f"SET temp_directory = {sql_path(output / 'tmp')}")

    def run(label: str, statement: str) -> None:
        started = time.monotonic()
        con.execute(statement)
        print(f"{label}: {time.monotonic() - started:.1f}s", flush=True)

    def csv(name: str) -> str:
        return f"read_csv({sql_path(data / 'data' / (name + '.csv'))}, header=true, all_varchar=true)"

    run(
        "Normalization functions",
        """
        CREATE OR REPLACE MACRO norm_postal(x) AS
          nullif(regexp_replace(upper(trim(x)), '[^A-Z0-9]', '', 'g'), '');
        CREATE OR REPLACE MACRO norm_phone(x) AS
          CASE
            WHEN length(regexp_replace(coalesce(x, ''), '[^0-9]', '', 'g')) = 10
              THEN regexp_replace(x, '[^0-9]', '', 'g')
            WHEN length(regexp_replace(coalesce(x, ''), '[^0-9]', '', 'g')) = 11
              AND left(regexp_replace(x, '[^0-9]', '', 'g'), 1) = '1'
              THEN right(regexp_replace(x, '[^0-9]', '', 'g'), 10)
            ELSE NULL
          END;
        CREATE OR REPLACE MACRO norm_dob(x) AS
          CAST(try_strptime(x, ['%Y-%m-%d', '%d-%m-%Y', '%Y/%m/%d', '%Y%m%d', '%m/%d/%Y']) AS DATE);
        CREATE OR REPLACE MACRO norm_name(x) AS
          trim(regexp_replace(upper(coalesce(x, '')), '[^A-Z]+', ' ', 'g'));
        """,
    )

    run(
        "Curated CRM",
        f"""
        CREATE OR REPLACE TABLE crm_silver AS
        SELECT
          nullif(trim(crm_customer_id), '') AS crm_id,
          nullif(trim(duplicate_of_crm_id), '') AS duplicate_of_id,
          CASE WHEN length(trim(national_id_hash)) = 64 THEN lower(trim(national_id_hash)) END AS id_hash,
          coalesce(norm_dob(date_of_birth), norm_dob(dob_raw)) AS dob,
          norm_postal(coalesce(nullif(trim(postal_code), ''), postal_code_raw)) AS postal,
          norm_phone(coalesce(nullif(trim(primary_phone_e164), ''), primary_phone_raw)) AS phone,
          norm_name(last_name) AS surname,
          coalesce(try_cast(consent_call AS BOOLEAN), false) AS consent_call,
          coalesce(try_cast(consent_sms AS BOOLEAN), false) AS consent_sms,
          coalesce(try_cast(consent_email AS BOOLEAN), false) AS consent_email,
          last_profile_update_ts, extract_ts, batch_id,
          row_number() OVER (
            PARTITION BY crm_customer_id
            ORDER BY last_profile_update_ts DESC NULLS LAST, extract_ts DESC NULLS LAST
          ) AS version_rank
        FROM {csv('customers')};

        CREATE OR REPLACE TABLE crm_unique AS
        SELECT * EXCLUDE (version_rank)
        FROM crm_silver WHERE crm_id IS NOT NULL AND version_rank = 1;

        CREATE OR REPLACE TABLE crm_resolved AS
        SELECT c.*,
          'G-' || substr(sha256(
            CASE
              WHEN c.id_hash IS NOT NULL THEN 'N:' || c.id_hash
              WHEN p.id_hash IS NOT NULL THEN 'N:' || p.id_hash
              ELSE 'C:' || coalesce(c.duplicate_of_id, c.crm_id)
            END
          ), 1, 20) AS golden_customer_id
        FROM crm_unique c
        LEFT JOIN crm_unique p ON c.duplicate_of_id = p.crm_id;
        """,
    )

    run(
        "Curated source profiles",
        f"""
        CREATE OR REPLACE TABLE source_profiles AS
        SELECT 'cards' AS source_system,
          nullif(trim(src_customer_ref), '') AS source_customer_id,
          norm_dob(cardholder_dob_raw) AS dob,
          norm_postal(cardholder_postal_raw) AS postal,
          norm_phone(cardholder_phone_raw) AS phone,
          norm_name(cardholder_name_raw) AS name
        FROM {csv('card_accounts')}
        QUALIFY row_number() OVER (
          PARTITION BY src_customer_ref ORDER BY snapshot_date DESC NULLS LAST,
            extract_ts DESC NULLS LAST, card_account_id, record_hash
        ) = 1
        UNION ALL
        SELECT 'lending', nullif(trim(src_customer_ref), ''),
          norm_dob(borrower_dob_raw), norm_postal(borrower_postal_raw),
          norm_phone(borrower_phone_raw), norm_name(borrower_name_raw)
        FROM {csv('loan_accounts')}
        QUALIFY row_number() OVER (
          PARTITION BY src_customer_ref ORDER BY snapshot_date DESC NULLS LAST,
            extract_ts DESC NULLS LAST, loan_id, record_hash
        ) = 1
        UNION ALL
        SELECT 'core_banking', nullif(trim(src_customer_ref), ''),
          norm_dob(holder_dob_raw), norm_postal(holder_postal_raw),
          norm_phone(holder_phone_raw), norm_name(holder_name_raw)
        FROM {csv('deposit_accounts')}
        QUALIFY row_number() OVER (
          PARTITION BY src_customer_ref ORDER BY snapshot_date DESC NULLS LAST,
            extract_ts DESC NULLS LAST, deposit_account_id, record_hash
        ) = 1
        UNION ALL
        SELECT 'core_banking', nullif(trim(bank_subject_ref), ''),
          norm_dob(subject_dob_reported),
          norm_postal(regexp_extract(coalesce(subject_address_reported, ''),
            '([A-Za-z][0-9][A-Za-z][ -]?[0-9][A-Za-z][0-9])', 1)),
          NULL, norm_name(subject_name_reported)
        FROM {csv('external')}
        QUALIFY row_number() OVER (
          PARTITION BY bank_subject_ref ORDER BY pull_date DESC NULLS LAST,
            file_received_ts DESC NULLS LAST, bureau_request_id, record_hash
        ) = 1;
        """,
    )

    run(
        "Block on DOB and postcode or phone",
        """
        CREATE OR REPLACE TABLE crm_match_keys AS
        SELECT 'postal' AS key_type, dob, postal AS key_value,
          golden_customer_id, surname
        FROM crm_resolved WHERE dob IS NOT NULL AND postal IS NOT NULL
        UNION ALL
        SELECT 'phone', dob, phone, golden_customer_id, surname
        FROM crm_resolved WHERE dob IS NOT NULL AND phone IS NOT NULL;

        CREATE OR REPLACE TABLE source_match_keys AS
        SELECT source_system, source_customer_id, 'postal' AS key_type,
          dob, postal AS key_value, name
        FROM source_profiles
        WHERE source_customer_id IS NOT NULL AND dob IS NOT NULL AND postal IS NOT NULL
        UNION ALL
        SELECT source_system, source_customer_id, 'phone', dob, phone, name
        FROM source_profiles
        WHERE source_customer_id IS NOT NULL AND dob IS NOT NULL AND phone IS NOT NULL;

        CREATE OR REPLACE TABLE candidate_evidence AS
        SELECT s.source_system, s.source_customer_id, c.golden_customer_id,
          max(CASE WHEN s.key_type = 'postal' THEN 1 ELSE 0 END) AS postal_match,
          max(CASE WHEN s.key_type = 'phone' THEN 1 ELSE 0 END) AS phone_match,
          max(CASE WHEN c.surname <> '' AND
            contains(' ' || s.name || ' ', ' ' || c.surname || ' ')
            THEN 1 ELSE 0 END) AS surname_match
        FROM source_match_keys s
        JOIN crm_match_keys c
          ON s.key_type = c.key_type AND s.dob = c.dob AND s.key_value = c.key_value
        GROUP BY s.source_system, s.source_customer_id, c.golden_customer_id;

        CREATE OR REPLACE TABLE source_conflicts AS
        SELECT source_system, source_customer_id,
          count(DISTINCT dob) FILTER (WHERE dob IS NOT NULL) > 1
            OR count(DISTINCT postal) FILTER (WHERE postal IS NOT NULL) > 1 AS conflicting_profile
        FROM source_profiles WHERE source_customer_id IS NOT NULL
        GROUP BY source_system, source_customer_id;

        CREATE OR REPLACE TABLE ranked_candidates AS
        SELECT *,
          row_number() OVER (
            PARTITION BY source_system, source_customer_id
            ORDER BY match_confidence DESC, golden_customer_id
          ) AS candidate_rank,
          lead(match_confidence) OVER (
            PARTITION BY source_system, source_customer_id
            ORDER BY match_confidence DESC, golden_customer_id
          ) AS second_confidence
        FROM (
          SELECT *, CASE
            WHEN surname_match = 1 AND postal_match = 1 AND phone_match = 1 THEN 0.99
            WHEN surname_match = 1 AND postal_match = 1 THEN 0.97
            WHEN surname_match = 1 AND phone_match = 1 THEN 0.96
            WHEN postal_match = 1 AND phone_match = 1 THEN 0.90
            ELSE 0.82 END AS match_confidence
          FROM candidate_evidence
        );
        """,
    )

    run(
        "Identity crosswalk",
        f"""
        CREATE OR REPLACE TABLE crm_crosswalk AS
        SELECT 'crm' AS source_system, crm_id AS source_customer_id,
          golden_customer_id, 'crm_anchor' AS match_method,
          1.0 AS match_confidence, 'linked' AS link_status,
          DATE '{SNAPSHOT_DATE}' AS as_of_date,
          golden_customer_id AS candidate_golden_customer_id
        FROM crm_resolved;

        CREATE OR REPLACE TABLE product_crosswalk AS
        SELECT s.source_system, s.source_customer_id,
          CASE WHEN r.match_confidence >= 0.95
                 AND (r.second_confidence IS NULL OR r.match_confidence - r.second_confidence >= 0.05)
                 AND NOT coalesce(f.conflicting_profile, false)
            THEN r.golden_customer_id END AS golden_customer_id,
          CASE WHEN r.golden_customer_id IS NULL THEN 'no_match'
               WHEN coalesce(f.conflicting_profile, false) THEN 'conflicting_profile'
               ELSE 'dob_postal_phone_name' END AS match_method,
          coalesce(r.match_confidence, 0.0) AS match_confidence,
          CASE WHEN r.golden_customer_id IS NULL THEN 'unlinked'
               WHEN r.match_confidence >= 0.95
                 AND (r.second_confidence IS NULL OR r.match_confidence - r.second_confidence >= 0.05)
                 AND NOT coalesce(f.conflicting_profile, false) THEN 'linked'
               ELSE 'review_pending' END AS link_status,
          DATE '{SNAPSHOT_DATE}' AS as_of_date,
          r.golden_customer_id AS candidate_golden_customer_id
        FROM (SELECT DISTINCT source_system, source_customer_id FROM source_profiles
              WHERE source_customer_id IS NOT NULL) s
        LEFT JOIN ranked_candidates r
          ON s.source_system = r.source_system
          AND s.source_customer_id = r.source_customer_id AND r.candidate_rank = 1
        LEFT JOIN source_conflicts f
          ON s.source_system = f.source_system AND s.source_customer_id = f.source_customer_id;

        CREATE OR REPLACE TABLE account_lookup AS
        SELECT account_id, min(source_system) AS source_system,
          min(source_customer_id) AS source_customer_id
        FROM (
          SELECT card_account_id AS account_id, 'cards' AS source_system,
            src_customer_ref AS source_customer_id FROM {csv('card_accounts')}
          UNION ALL
          SELECT loan_id, 'lending', src_customer_ref FROM {csv('loan_accounts')}
          UNION ALL
          SELECT deposit_account_id, 'core_banking', src_customer_ref FROM {csv('deposit_accounts')}
        )
        WHERE nullif(trim(account_id), '') IS NOT NULL
        GROUP BY account_id
        HAVING count(DISTINCT source_system || ':' || source_customer_id) = 1;

        CREATE OR REPLACE TABLE case_match_evidence AS
        SELECT c.case_id, nullif(trim(c.coll_customer_ref), '') AS coll_customer_ref,
          x.golden_customer_id AS crm_golden,
          px.golden_customer_id AS account_golden
        FROM {csv('collections_cases')} c
        LEFT JOIN crm_crosswalk x ON x.source_customer_id = c.coll_customer_ref
        LEFT JOIN account_lookup a ON a.account_id = c.primary_account_id
        LEFT JOIN product_crosswalk px
          ON px.source_system = a.source_system
          AND px.source_customer_id = a.source_customer_id
          AND px.link_status = 'linked';

        CREATE OR REPLACE TABLE collections_crosswalk AS
        WITH evidence AS (
          SELECT coll_customer_ref,
            min(crm_golden) AS crm_golden,
            min(account_golden) AS account_golden,
            count(*) AS case_count,
            count(account_golden) AS account_linked_count,
            count(DISTINCT coalesce(crm_golden, account_golden)) AS candidate_count,
            bool_or(crm_golden IS NOT NULL AND account_golden IS NOT NULL
              AND crm_golden <> account_golden) AS has_conflict
          FROM case_match_evidence WHERE coll_customer_ref IS NOT NULL
          GROUP BY coll_customer_ref
        ), resolved AS (
          SELECT *, coalesce(crm_golden, account_golden) AS candidate_golden_customer_id,
            candidate_count = 1 AND NOT has_conflict
              AND (crm_golden IS NOT NULL OR account_linked_count = case_count) AS can_link
          FROM evidence
        )
        SELECT 'collections' AS source_system,
          coll_customer_ref AS source_customer_id,
          CASE WHEN can_link THEN candidate_golden_customer_id END AS golden_customer_id,
          CASE WHEN has_conflict OR candidate_count > 1 THEN 'conflicting_case_evidence'
               WHEN crm_golden IS NOT NULL THEN 'crm_reference'
               WHEN account_golden IS NOT NULL THEN 'account_fallback'
               ELSE 'no_match' END AS match_method,
          CASE WHEN crm_golden IS NOT NULL THEN 1.0
               WHEN account_golden IS NOT NULL THEN 0.98 ELSE 0.0 END AS match_confidence,
          CASE WHEN can_link THEN 'linked'
               WHEN candidate_golden_customer_id IS NOT NULL THEN 'review_pending'
               ELSE 'unlinked' END AS link_status,
          DATE '{SNAPSHOT_DATE}' AS as_of_date,
          candidate_golden_customer_id
        FROM resolved;

        CREATE OR REPLACE TABLE identity_crosswalk AS
        SELECT * FROM crm_crosswalk
        UNION ALL SELECT * FROM product_crosswalk
        UNION ALL SELECT * FROM collections_crosswalk;
        """,
    )

    run(
        "Golden customer table",
        f"""
        CREATE OR REPLACE TABLE case_rollup AS
        SELECT x.golden_customer_id,
          count(*) AS open_case_count,
          max(try_cast(c.current_dpd AS INTEGER)) AS max_current_dpd,
          sum(greatest(coalesce(try_cast(c.total_overdue AS DECIMAL(18,2)), 0), 0)) AS total_overdue_cad,
          bool_or(coalesce(try_cast(c.hardship_flag AS BOOLEAN), false)) AS hardship_flag
        FROM {csv('collections_cases')} c
        JOIN identity_crosswalk x
          ON x.source_system = 'collections' AND x.source_customer_id = c.coll_customer_ref
        WHERE c.case_status = 'open' AND x.link_status = 'linked'
          AND coalesce(try_cast(c.total_overdue AS DECIMAL(18,2)), 0) >= 0
          AND coalesce(try_cast(c.current_dpd AS INTEGER), 0) >= 0
        GROUP BY x.golden_customer_id;

        CREATE OR REPLACE TABLE golden_customers AS
        SELECT r.golden_customer_id, DATE '{SNAPSHOT_DATE}' AS as_of_date,
          list_sort(list(DISTINCT r.crm_id)) AS crm_customer_ids,
          coalesce(m.min_match_confidence, 1.0) AS min_match_confidence,
          coalesce(c.open_case_count, 0) AS open_case_count,
          c.max_current_dpd,
          coalesce(c.total_overdue_cad, 0)::DECIMAL(18,2) AS total_overdue_cad,
          coalesce(c.hardship_flag, false) AS hardship_flag,
          bool_and(r.consent_call) AS consent_call,
          bool_and(r.consent_sms) AS consent_sms,
          bool_and(r.consent_email) AS consent_email,
          CASE WHEN bool_or(r.dob IS NULL OR r.postal IS NULL) THEN 'needs_review'
               ELSE 'passed' END AS dq_status
        FROM crm_resolved r
        LEFT JOIN (
          SELECT golden_customer_id, min(match_confidence) AS min_match_confidence
          FROM identity_crosswalk WHERE link_status = 'linked'
          GROUP BY golden_customer_id
        ) m ON r.golden_customer_id = m.golden_customer_id
        LEFT JOIN case_rollup c ON r.golden_customer_id = c.golden_customer_id
        GROUP BY r.golden_customer_id, m.min_match_confidence,
          c.open_case_count, c.max_current_dpd, c.total_overdue_cad, c.hardship_flag;
        """,
    )

    checks = {
        "case_rows": f"SELECT count(*) FROM {csv('collections_cases')}",
        "golden_rows": "SELECT count(*) FROM golden_customers",
        "crm_records_collapsed": "SELECT count(*) - count(DISTINCT golden_customer_id) FROM crm_resolved",
        "duplicate_golden_ids": "SELECT count(*) - count(DISTINCT golden_customer_id) FROM golden_customers",
        "null_golden_ids": "SELECT count(*) FROM golden_customers WHERE golden_customer_id IS NULL",
        "duplicate_source_keys": "SELECT count(*) - count(DISTINCT source_system || ':' || source_customer_id) FROM identity_crosswalk",
        "orphan_linked_ids": """SELECT count(*) FROM identity_crosswalk x
            LEFT JOIN golden_customers g ON x.golden_customer_id = g.golden_customer_id
            WHERE x.link_status = 'linked' AND g.golden_customer_id IS NULL""",
        "invalid_confidence": "SELECT count(*) FROM identity_crosswalk WHERE match_confidence NOT BETWEEN 0 AND 1",
        "invalid_overdue": "SELECT count(*) FROM golden_customers WHERE total_overdue_cad < 0",
        "invalid_case_amounts": f"""SELECT count(*) FROM {csv('collections_cases')}
            WHERE try_cast(total_overdue AS DECIMAL(18,2)) < 0
               OR try_cast(current_dpd AS INTEGER) < 0""",
        "crm_missing_id": "SELECT count(*) FROM crm_silver WHERE crm_id IS NULL",
        "crm_duplicate_rows": "SELECT count(*) - count(DISTINCT crm_id) FROM crm_silver WHERE crm_id IS NOT NULL",
        "crm_missing_dob": "SELECT count(*) FROM crm_unique WHERE dob IS NULL",
        "crm_missing_postal": "SELECT count(*) FROM crm_unique WHERE postal IS NULL",
        "crm_needs_review": "SELECT count(*) FROM golden_customers WHERE dq_status = 'needs_review'",
        "case_account_conflicts": """SELECT count(*) FROM case_match_evidence
            WHERE crm_golden IS NOT NULL AND account_golden IS NOT NULL
              AND crm_golden <> account_golden""",
        "account_fallback_links": """SELECT count(*) FROM collections_crosswalk
            WHERE match_method = 'account_fallback' AND link_status = 'linked'""",
        "unresolved_case_refs": f"""SELECT count(*) FROM {csv('collections_cases')} c
            LEFT JOIN identity_crosswalk x ON x.source_system = 'collections'
              AND x.source_customer_id = c.coll_customer_ref
            WHERE x.golden_customer_id IS NULL""",
    }
    report = {name: con.execute(query).fetchone()[0] for name, query in checks.items()}
    report["case_resolution_pct"] = round(
        100 * (1 - report["unresolved_case_refs"] / report["case_rows"]), 3
    )
    report["source_link_status"] = [
        dict(zip(("source_system", "link_status", "count"), row))
        for row in con.execute("""
            SELECT source_system, link_status, count(*)
            FROM identity_crosswalk GROUP BY 1, 2 ORDER BY 1, 2
        """).fetchall()
    ]
    validate_publication(con, report)

    for table, filename in (
        ("crm_unique", "silver_customers.parquet"),
        ("source_profiles", "silver_source_profiles.parquet"),
        ("identity_crosswalk", "identity_crosswalk.parquet"),
        ("golden_customers", "golden_customers.parquet"),
    ):
        target = output / filename
        if target.exists():
            target.unlink()
        run(f"Write {filename}", f"COPY {table} TO {sql_path(target)} (FORMAT PARQUET)")
    (output / "quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# C360 data quality report", "", f"Snapshot: {SNAPSHOT_DATE}", "",
        "Generated by `src/c360/build.py` from the synthetic Maple release.", "",
        f"Golden customers: {report['golden_rows']:,}; case resolution: {report['case_resolution_pct']}%.",
        "The release describes 1,000,000 people. The extra golden IDs are kept separate pending review rather than merged on weak evidence.",
        "", "## Issues and handling", "",
        "Counts can overlap because a case or customer can have more than one issue.", "",
        "| Issue | Affected rows | Handling |", "| --- | ---: | --- |",
        f"| CRM rows without DOB | {report['crm_missing_dob']:,} | Keep in C360; mark customer for review; never use DOB-based automatic source matching. |",
        f"| CRM rows without postcode | {report['crm_missing_postal']:,} | Keep in C360; use DOB plus phone and surname only when unique, otherwise review. |",
        f"| Golden customers needing profile review | {report['crm_needs_review']:,} | One or more CRM records in the customer group lack a usable DOB or postcode. Preserve the customer and set `dq_status = needs_review`; missing evidence cannot justify an automatic source match. This is a customer count, separate from `review_pending` source links below. |",
        f"| Cases with conflicting CRM and account identity | {report['case_account_conflicts']:,} | Quarantine from customer-level rollups and decisions. |",
        f"| Cases without a published customer link | {report['unresolved_case_refs']:,} | Exclude from customer-level rollups; retain for steward review. |",
        f"| Cases with invalid overdue or DPD | {report['invalid_case_amounts']:,} | Report for source correction; exclude invalid values from golden rollups. |",
        f"| CRM records collapsed into existing golden identities | {report['crm_records_collapsed']:,} | Link by exact national ID hash or explicit duplicate reference. |",
        f"| Duplicate golden IDs | {report['duplicate_golden_ids']:,} | Fail publication if nonzero. |",
        f"| Duplicate source keys | {report['duplicate_source_keys']:,} | Fail publication if nonzero. |",
        "", "## Identity links", "", "| Source | Status | Count |", "| --- | --- | ---: |",
    ]
    lines += [f"| {row['source_system']} | {row['link_status']} | {row['count']:,} |"
              for row in report["source_link_status"]]
    lines += ["", "Unlinked and review-pending source keys remain outside customer-level joins."]
    (output / "quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    con.close()


if __name__ == "__main__":
    main()
