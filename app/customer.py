"""Read only the published, linked customer scope needed by the demo page."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

from src.c360.explain import explain_customer


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "maple_data/maple_collections_release"
C360 = ROOT / "local_artifacts/c360"
GOLDEN_ID = re.compile(r"^G-[0-9a-f]{20}$")


def _path(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def _records(con: duckdb.DuckDBPyConnection, sql: str, values: list) -> list[dict]:
    cursor = con.execute(sql, values)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def load_customer(
    golden_id: str, dataset_root: Path = DATASET, c360_root: Path = C360,
) -> dict:
    """Return approved customer context; all event joins require linked C360 keys."""
    if not GOLDEN_ID.fullmatch(golden_id):
        raise ValueError("Enter a golden ID in the form G- followed by 20 hex characters")
    data = Path(dataset_root) / "data"
    c360 = Path(c360_root)
    required = [c360 / "golden_customers.parquet", c360 / "identity_crosswalk.parquet"]
    required += [data / f"{name}.csv" for name in (
        "card_accounts", "loan_accounts", "deposit_accounts", "collections_cases",
        "contact_history", "promises_to_pay",
    )]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"Missing {path}; run the dataset and C360 setup first")

    con = duckdb.connect(":memory:")
    try:
        con.execute(f"CREATE VIEW gold AS SELECT * FROM read_parquet({_path(c360 / 'golden_customers.parquet')})")
        con.execute(f"CREATE VIEW links AS SELECT * FROM read_parquet({_path(c360 / 'identity_crosswalk.parquet')})")
        for name in ("card_accounts", "loan_accounts", "deposit_accounts",
                     "collections_cases", "contact_history", "promises_to_pay"):
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_csv({_path(data / (name + '.csv'))}, header=true, all_varchar=true)")

        summary = _records(con, """SELECT golden_customer_id, as_of_date,
            len(crm_customer_ids) AS crm_record_count, min_match_confidence,
            open_case_count, max_current_dpd, total_overdue_cad,
            hardship_flag, dq_status
            FROM gold WHERE golden_customer_id = ?""", [golden_id])
        if not summary:
            return {"golden_customer_id": golden_id, "found": False}

        account_queries = {
            "cards": """SELECT a.card_account_id AS account_id, a.snapshot_date,
                a.product_code AS product, a.account_status AS status,
                try_cast(a.current_balance AS DECIMAL(18,2)) AS balance_cad,
                try_cast(a.dpd AS INTEGER) AS dpd
                FROM card_accounts a JOIN links x
                  ON x.source_system = 'cards' AND x.source_customer_id = a.src_customer_ref
                WHERE x.golden_customer_id = ? AND x.link_status = 'linked'
                ORDER BY a.snapshot_date DESC, a.card_account_id LIMIT 50""",
            "lending": """SELECT a.loan_id AS account_id, a.snapshot_date,
                a.product_type AS product, a.dpd_bucket AS status,
                try_cast(a.principal_balance AS DECIMAL(18,2)) AS balance_cad,
                try_cast(a.dpd AS INTEGER) AS dpd
                FROM loan_accounts a JOIN links x
                  ON x.source_system = 'lending' AND x.source_customer_id = a.src_customer_ref
                WHERE x.golden_customer_id = ? AND x.link_status = 'linked'
                ORDER BY a.snapshot_date DESC, a.loan_id LIMIT 50""",
            "deposits": """SELECT a.deposit_account_id AS account_id, a.snapshot_date,
                a.product_type AS product, a.account_status AS status,
                try_cast(a.current_balance AS DECIMAL(18,2)) AS balance_cad,
                try_cast(a.overdraft_dpd AS INTEGER) AS dpd
                FROM deposit_accounts a JOIN links x
                  ON x.source_system = 'core_banking' AND x.source_customer_id = a.src_customer_ref
                WHERE x.golden_customer_id = ? AND x.link_status = 'linked'
                ORDER BY a.snapshot_date DESC, a.deposit_account_id LIMIT 50""",
        }
        accounts = {name: _records(con, sql, [golden_id])
                    for name, sql in account_queries.items()}
        con.execute("""CREATE VIEW customer_cases AS
            SELECT x.golden_customer_id, c.case_id, c.case_open_date, c.case_status, c.current_bucket,
                   try_cast(c.current_dpd AS INTEGER) AS current_dpd,
                   try_cast(c.total_overdue AS DECIMAL(18,2)) AS overdue_cad,
                   try_cast(c.hardship_flag AS BOOLEAN) AS hardship_flag,
                   c.coll_customer_ref
            FROM collections_cases c JOIN links x
              ON x.source_system = 'collections'
             AND x.source_customer_id = c.coll_customer_ref
            WHERE x.link_status = 'linked'""")
        cases = _records(con, """SELECT case_id, case_open_date, case_status,
            current_bucket, current_dpd, overdue_cad, hardship_flag
            FROM customer_cases WHERE golden_customer_id = ?
            ORDER BY case_open_date DESC, case_id LIMIT 50""", [golden_id])
        contacts = _records(con, """SELECT h.contact_id, h.case_id,
            h.contact_ts_local, coalesce(nullif(h.channel_v2, ''), h.channel) AS channel,
            h.direction, h.outcome_code
            FROM contact_history h JOIN customer_cases c ON c.case_id = h.case_id
              AND c.golden_customer_id = ?
            JOIN links crm ON crm.source_system = 'crm'
              AND crm.source_customer_id = h.crm_customer_id
              AND crm.golden_customer_id = ? AND crm.link_status = 'linked'
            ORDER BY h.contact_ts_local DESC, h.contact_id LIMIT 50""", [golden_id, golden_id])
        promises = _records(con, """SELECT p.ptp_id, p.case_id, p.ptp_created_ts,
            p.ptp_due_date, try_cast(p.ptp_amount AS DECIMAL(18,2)) AS amount_cad,
            p.ptp_status
            FROM promises_to_pay p JOIN customer_cases c ON c.case_id = p.case_id
              AND c.golden_customer_id = ?
            JOIN links crm ON crm.source_system = 'crm'
              AND crm.source_customer_id = p.crm_customer_id
              AND crm.golden_customer_id = ? AND crm.link_status = 'linked'
            ORDER BY p.ptp_created_ts DESC, p.ptp_id LIMIT 50""", [golden_id, golden_id])
        return {
            "golden_customer_id": golden_id,
            "found": True,
            "summary": summary[0],
            "accounts": accounts,
            "cases": cases,
            "contacts": contacts,
            "promises": promises,
            "identity": explain_customer(golden_id, c360),
        }
    finally:
        con.close()
