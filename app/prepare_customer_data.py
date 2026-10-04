"""Build the optional indexed customer-page cache from the downloaded release.

Run once from the repo root: python -m app.prepare_customer_data
The cache is ignored by Git and contains only columns the Customer page uses.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from app.customer import C360, DATASET, _path


CACHE = C360 / "customer_page.duckdb"
SOURCES = {
    "card_accounts": ("card_account_id", "snapshot_date", "product_code",
                      "account_status", "current_balance", "dpd", "src_customer_ref"),
    "loan_accounts": ("loan_id", "snapshot_date", "product_type", "dpd_bucket",
                      "principal_balance", "dpd", "src_customer_ref"),
    "deposit_accounts": ("deposit_account_id", "snapshot_date", "product_type",
                         "account_status", "current_balance", "overdraft_dpd",
                         "src_customer_ref"),
    "collections_cases": ("case_id", "case_open_date", "case_status", "current_bucket",
                          "current_dpd", "total_overdue", "hardship_flag",
                          "coll_customer_ref"),
    "contact_history": ("contact_id", "case_id", "crm_customer_id",
                        "contact_ts_local", "channel_v2", "channel", "direction",
                        "outcome_code"),
    "promises_to_pay": ("ptp_id", "case_id", "crm_customer_id", "ptp_created_ts",
                        "ptp_due_date", "ptp_amount", "ptp_status"),
}
INDEXES = {
    "card_accounts": "src_customer_ref",
    "loan_accounts": "src_customer_ref",
    "deposit_accounts": "src_customer_ref",
    "collections_cases": "coll_customer_ref",
    "contact_history": "case_id",
    "promises_to_pay": "case_id",
}


def build(data_dir: Path = DATASET, cache_path: Path = CACHE,
          c360_root: Path = C360) -> Path:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_name(cache_path.stem + ".building.duckdb")
    if temporary.exists():
        temporary.unlink()
    con = duckdb.connect(str(temporary))
    try:
        con.execute("SET memory_limit='1GB'")
        con.execute("SET threads=2")
        for table, columns in SOURCES.items():
            source = data_dir / "data" / f"{table}.csv"
            if not source.is_file():
                raise FileNotFoundError(source)
            selected = ", ".join(columns)
            con.execute(f"CREATE TABLE {table} AS SELECT {selected} FROM "
                        f"read_csv({_path(source)}, header=true, all_varchar=true)")
            con.execute(f"CREATE INDEX idx_{table}_customer ON {table} ({INDEXES[table]})")
            print(f"Cached {table}: {con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:,} rows", flush=True)
        crosswalk = Path(c360_root) / "identity_crosswalk.parquet"
        if not crosswalk.is_file():
            raise FileNotFoundError(crosswalk)
        con.execute(f"CREATE VIEW linked_ids AS SELECT source_system, source_customer_id, "
                    f"golden_customer_id FROM read_parquet({_path(crosswalk)}) "
                    "WHERE link_status = 'linked' AND source_system IN ('crm', 'collections')")
        con.execute("""CREATE TABLE customer_activity AS
            SELECT crm.golden_customer_id,
                   count(*) AS promise_count,
                   count(*) FILTER (WHERE lower(p.ptp_status) = 'broken') AS broken_promise_count,
                   count(*) FILTER (WHERE lower(p.ptp_status) = 'open') AS open_promise_count
            FROM promises_to_pay p
            JOIN collections_cases c ON c.case_id = p.case_id
            JOIN linked_ids crm ON crm.source_system = 'crm'
                AND crm.source_customer_id = p.crm_customer_id
            JOIN linked_ids coll ON coll.source_system = 'collections'
                AND coll.source_customer_id = c.coll_customer_ref
                AND coll.golden_customer_id = crm.golden_customer_id
            GROUP BY crm.golden_customer_id""")
        con.execute("CREATE UNIQUE INDEX idx_activity_customer ON customer_activity (golden_customer_id)")
        print(f"Cached promise activity: {con.execute('SELECT count(*) FROM customer_activity').fetchone()[0]:,} customers", flush=True)
        con.execute("CHECKPOINT")
    finally:
        con.close()
    temporary.replace(cache_path)
    return cache_path


if __name__ == "__main__":
    print(build())
