import json

from app.c360_coverage import coverage_snapshot


def test_coverage_keeps_people_and_source_record_counts_separate(tmp_path):
    report = {
        "golden_rows": 10,
        "crm_needs_review": 2,
        "unresolved_case_refs": 1,
        "case_rows": 20,
        "source_link_status": [
            {"source_system": "crm", "link_status": "linked", "count": 10},
            {"source_system": "cards", "link_status": "review_pending", "count": 3},
            {"source_system": "cards", "link_status": "unlinked", "count": 4},
        ],
    }
    (tmp_path / "quality_report.json").write_text(json.dumps(report), encoding="utf-8")

    result = coverage_snapshot(tmp_path)

    assert result["golden_customers"] == 10
    assert result["passed_customers"] == 8
    assert result["needs_review_customers"] == 2
    assert result["review_pending_source_records"] == 3
    assert result["unlinked_source_records"] == 4
    assert result["cases_without_link"] == 1
