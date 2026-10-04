import csv

import duckdb

from app.prepare_customer_data import SOURCES, build


def test_indexed_customer_cache_uses_only_page_columns(tmp_path):
    data_dir = tmp_path / "release" / "data"
    data_dir.mkdir(parents=True)
    for table, columns in SOURCES.items():
        with (data_dir / f"{table}.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=[*columns, "ccb_deposit_flag"])
            writer.writeheader()
            writer.writerow({**{column: "1" for column in columns},
                             **({"ptp_status": "broken"} if table == "promises_to_pay" else {}),
                             "ccb_deposit_flag": "true"})

    con = duckdb.connect()
    try:
        con.execute(f"""COPY (SELECT * FROM (VALUES
            ('crm', '1', 'G-aaaaaaaaaaaaaaaaaaaa', 'linked'),
            ('collections', '1', 'G-aaaaaaaaaaaaaaaaaaaa', 'linked')
        ) AS t(source_system, source_customer_id, golden_customer_id, link_status))
        TO '{(tmp_path / 'identity_crosswalk.parquet').as_posix()}' (FORMAT PARQUET)""")
    finally:
        con.close()

    path = build(tmp_path / "release", tmp_path / "customer_page.duckdb", tmp_path)
    con = duckdb.connect(str(path), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM contact_history").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM deposit_accounts").fetchone()[0] == 1
        columns = {row[1] for row in con.execute("PRAGMA table_info('deposit_accounts')").fetchall()}
        assert "ccb_deposit_flag" not in columns
        assert con.execute("SELECT promise_count, broken_promise_count "
                           "FROM customer_activity").fetchone() == (1, 1)
    finally:
        con.close()
