"""Layer 1 publication checks, including deliberate bad input."""

from pathlib import Path

import duckdb
import pytest

from src.c360.quality import validate_publication


def good_report() -> dict[str, int]:
    return {
        "duplicate_golden_ids": 0, "null_golden_ids": 0,
        "duplicate_source_keys": 0, "orphan_linked_ids": 0,
        "invalid_confidence": 0, "invalid_overdue": 0,
        "unresolved_case_refs": 0, "case_rows": 100,
    }


@pytest.fixture
def tables() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE golden_customers (golden_customer_id VARCHAR)")
    con.execute("""CREATE TABLE identity_crosswalk (
        source_system VARCHAR, source_customer_id VARCHAR,
        golden_customer_id VARCHAR, match_confidence DOUBLE,
        link_status VARCHAR
    )""")
    con.execute("INSERT INTO golden_customers VALUES ('G-1')")
    con.execute("""INSERT INTO identity_crosswalk VALUES
        ('crm', 'C-1', 'G-1', 1.0, 'linked'),
        ('cards', 'A-1', NULL, 0.82, 'review_pending')""")
    yield con
    con.close()


def test_valid_link_and_quarantined_weak_match(tables: duckdb.DuckDBPyConnection) -> None:
    validate_publication(tables, good_report())
    assert tables.execute("""SELECT golden_customer_id FROM identity_crosswalk
        WHERE source_customer_id = 'A-1'""").fetchone()[0] is None


def test_low_confidence_published_link_is_rejected(tables: duckdb.DuckDBPyConnection) -> None:
    tables.execute("""UPDATE identity_crosswalk SET golden_customer_id = 'G-1',
        link_status = 'linked' WHERE source_customer_id = 'A-1'""")
    with pytest.raises(RuntimeError, match="Invalid published identity links"):
        validate_publication(tables, good_report())


def test_review_pending_link_cannot_publish_customer_id(tables: duckdb.DuckDBPyConnection) -> None:
    tables.execute("""UPDATE identity_crosswalk SET golden_customer_id = 'G-1'
        WHERE source_customer_id = 'A-1'""")
    with pytest.raises(RuntimeError, match="Invalid published identity links"):
        validate_publication(tables, good_report())


@pytest.mark.parametrize("failed_check", ["duplicate_golden_ids", "duplicate_source_keys"])
def test_duplicate_quality_gates_fail(
    tables: duckdb.DuckDBPyConnection, failed_check: str,
) -> None:
    report = good_report()
    report[failed_check] = 1
    with pytest.raises(RuntimeError, match=failed_check):
        validate_publication(tables, report)


def test_protected_column_is_rejected(tables: duckdb.DuckDBPyConnection) -> None:
    tables.execute("ALTER TABLE golden_customers ADD COLUMN citizenship VARCHAR")
    with pytest.raises(RuntimeError, match="Protected columns"):
        validate_publication(tables, good_report())


def test_case_resolution_gate_fails(tables: duckdb.DuckDBPyConnection) -> None:
    report = good_report()
    report["unresolved_case_refs"] = 1
    with pytest.raises(RuntimeError, match="Case-resolution"):
        validate_publication(tables, report)


def test_published_outputs_match_report_when_available() -> None:
    output = Path("local_artifacts/c360")
    golden = output / "golden_customers.parquet"
    crosswalk = output / "identity_crosswalk.parquet"
    if not golden.is_file() or not crosswalk.is_file():
        pytest.skip("Run src/c360/build.py to create local C360 outputs")
    import json

    report = json.loads((output / "quality_report.json").read_text(encoding="utf-8"))
    con = duckdb.connect(":memory:")
    try:
        con.execute(f"CREATE VIEW golden_customers AS SELECT * FROM read_parquet('{golden.as_posix()}')")
        con.execute(f"CREATE VIEW identity_crosswalk AS SELECT * FROM read_parquet('{crosswalk.as_posix()}')")
        assert con.execute("SELECT count(*) FROM golden_customers").fetchone()[0] == report["golden_rows"]
        assert con.execute("""SELECT count(*) - count(DISTINCT golden_customer_id)
            FROM golden_customers""").fetchone()[0] == 0
        assert con.execute("""SELECT count(*) - count(DISTINCT
            source_system || ':' || source_customer_id) FROM identity_crosswalk""").fetchone()[0] == 0
        validate_publication(con, report)
    finally:
        con.close()
