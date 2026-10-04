import csv

import duckdb

from app.dashboard import portfolio_snapshot


def test_portfolio_snapshot_counts_only_open_cases_and_promises(tmp_path):
    data = tmp_path / "release" / "data"
    data.mkdir(parents=True)
    with (data / "collections_cases.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_status", "case_open_date",
                                                    "current_dpd", "total_overdue", "queue"])
        writer.writeheader()
        writer.writerows([
            {"case_status": "open", "case_open_date": "2026-09-01", "current_dpd": 40,
             "total_overdue": 100, "queue": "mid_stage"},
            {"case_status": "closed", "case_open_date": "2026-09-02", "current_dpd": 90,
             "total_overdue": 999, "queue": "late_stage"},
            {"case_status": "open", "case_open_date": "2026-09-03", "current_dpd": 95,
             "total_overdue": 200, "queue": "late_stage"},
        ])
    with (data / "promises_to_pay.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["ptp_status"])
        writer.writeheader()
        writer.writerows([{"ptp_status": "open"}, {"ptp_status": "kept"}])
    gold = tmp_path / "c360"
    gold.mkdir()
    con = duckdb.connect()
    try:
        con.execute(f"COPY (SELECT '2026-09-28' AS as_of_date) TO "
                    f"'{(gold / 'golden_customers.parquet').as_posix()}' (FORMAT PARQUET)")
    finally:
        con.close()

    snapshot = portfolio_snapshot(tmp_path / "release", gold)
    assert snapshot["open_cases"] == 2
    assert snapshot["overdue_cad"] == 300
    assert snapshot["open_promises"] == 1
    assert snapshot["linked_customers"] == 1
    assert {row["bucket"]: row["cases"] for row in snapshot["buckets"]} == {
        "30–59 days": 1, "90+ days": 1,
    }
