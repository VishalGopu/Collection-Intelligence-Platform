"""Identity explanations use published evidence without printing personal attributes."""

from pathlib import Path

import duckdb
import pytest

from src.c360.explain import explain_customer


def test_explain_customer_shows_source_evidence(tmp_path: Path) -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute("""CREATE TABLE identity_crosswalk AS
            SELECT * FROM (VALUES
              ('crm', 'C-1', 'G-1', 'crm_anchor', 1.0, 'linked'),
              ('cards', 'A-1', 'G-1', 'dob_postal_phone_name', 0.99, 'linked'),
              ('lending', 'L-2', NULL, 'no_match', 0.82, 'review_pending')
            ) AS t(source_system, source_customer_id, golden_customer_id,
                   match_method, match_confidence, link_status)""")
        con.execute("""CREATE TABLE silver_customers AS SELECT
            'C-1' AS crm_id, 'G-1' AS golden_customer_id,
            DATE '1980-01-01' AS dob, 'A1A1A1' AS postal,
            '4165550100' AS phone, 'DOE' AS surname""")
        con.execute("""CREATE TABLE silver_source_profiles AS SELECT
            'cards' AS source_system, 'A-1' AS source_customer_id,
            DATE '1980-01-01' AS dob, 'A1A1A1' AS postal,
            '4165550100' AS phone, 'JANE DOE' AS name""")
        for name in (
            "identity_crosswalk", "silver_customers", "silver_source_profiles",
        ):
            path = (tmp_path / f"{name}.parquet").as_posix()
            con.execute(f"COPY {name} TO '{path}' (FORMAT PARQUET)")
    finally:
        con.close()

    result = explain_customer("G-1", tmp_path)
    assert len(result) == 2
    card = next(row for row in result if row["source_system"] == "cards")
    assert card["match_confidence"] == 0.99
    assert card["evidence"] == ["date of birth", "postcode", "phone", "surname"]
    assert "4165550100" not in str(result)
    assert "JANE DOE" not in str(result)
    assert explain_customer("G-missing", tmp_path) == []


def test_explain_published_customer_when_available() -> None:
    output = Path("local_artifacts/c360")
    golden = output / "golden_customers.parquet"
    if not golden.is_file():
        pytest.skip("Run src/c360/build.py to create local C360 outputs")
    con = duckdb.connect(":memory:")
    try:
        golden_id = con.execute(
            "SELECT golden_customer_id FROM read_parquet(?) LIMIT 1", [str(golden)]
        ).fetchone()[0]
    finally:
        con.close()
    result = explain_customer(golden_id, output)
    assert result
    assert any(row["source_system"] == "crm" for row in result)
    assert all(row["link_status"] == "linked" for row in result)
