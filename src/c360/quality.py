"""Publication checks for the golden C360 tables."""

from __future__ import annotations

from collections.abc import Mapping

import duckdb


PROTECTED_COLUMN_MARKERS = (
    "gender", "marital", "citizenship", "household", "newcomer",
    "accessibility", "vulnerab", "accent", "ethnic", "religion", "disability",
)


def validate_publication(con: duckdb.DuckDBPyConnection, report: Mapping[str, object]) -> None:
    """Fail before publishing if identity, privacy, or case-resolution rules fail."""
    for table in ("golden_customers", "identity_crosswalk"):
        columns = (row[0].lower() for row in con.execute(f"DESCRIBE {table}").fetchall())
        if any(marker in column for column in columns
               for marker in PROTECTED_COLUMN_MARKERS):
            raise RuntimeError(f"Protected columns in published {table} output")

    invalid_links = con.execute("""
        SELECT count(*) FROM identity_crosswalk
        WHERE (link_status = 'linked' AND
                 (golden_customer_id IS NULL OR match_confidence IS NULL
                  OR match_confidence < 0.95))
           OR (link_status <> 'linked' AND golden_customer_id IS NOT NULL)
           OR source_system IS NULL OR source_customer_id IS NULL
           OR link_status NOT IN ('linked', 'review_pending', 'unlinked')
           OR link_status IS NULL
    """).fetchone()[0]
    if invalid_links:
        raise RuntimeError(f"Invalid published identity links: {invalid_links}")

    for key in (
        "duplicate_golden_ids", "null_golden_ids", "duplicate_source_keys",
        "orphan_linked_ids", "invalid_confidence", "invalid_overdue",
    ):
        if report[key]:
            raise RuntimeError(f"Publish quality gate failed: {key}={report[key]}")
    if not report["case_rows"] or report["unresolved_case_refs"] / report["case_rows"] > 0.005:
        raise RuntimeError("Case-resolution quality gate failed")
