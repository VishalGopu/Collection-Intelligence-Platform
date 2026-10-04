"""Display-safe C360 publication counts from the generated quality report."""

from __future__ import annotations

import json
from pathlib import Path

from app.customer import C360


def coverage_snapshot(c360_root: Path = C360) -> dict:
    report_path = Path(c360_root) / "quality_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    statuses = {"linked": 0, "review_pending": 0, "unlinked": 0}
    for row in report["source_link_status"]:
        statuses[row["link_status"]] += int(row["count"])
    golden = int(report["golden_rows"])
    review = int(report["crm_needs_review"])
    if review > golden:
        raise ValueError("C360 quality report has more review customers than golden customers")
    return {
        "golden_customers": golden,
        "passed_customers": golden - review,
        "needs_review_customers": review,
        "cases_without_link": int(report["unresolved_case_refs"]),
        "total_cases": int(report["case_rows"]),
        "linked_source_records": statuses["linked"],
        "review_pending_source_records": statuses["review_pending"],
        "unlinked_source_records": statuses["unlinked"],
    }
