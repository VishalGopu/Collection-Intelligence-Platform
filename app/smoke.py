"""Exercise the three Streamlit tabs with the verified hero customer."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.customer import load_customer
from app.recommend import latest_audit_rows


HERO_ID = "G-39c6b287f70371cd9fc6"


def main() -> None:
    customer = load_customer(HERO_ID)
    assert customer["found"] and customer["cases"] and customer["contacts"]
    assert customer["promises"] and customer["identity"]["links"]

    app = AppTest.from_file(str(Path(__file__).with_name("main.py")), default_timeout=120).run()
    assert not app.exception and not app.error
    assert [tab.label for tab in app.tabs] == ["Customer", "Ask", "Recommendation"]
    assert app.text_input(key="golden_id").value == HERO_ID

    app.text_area(key="ask_question").set_value(
        "What is the average days past due of open cases by queue?"
    ).run()
    app.button(key="ask_submit").click().run()
    assert not app.exception and not app.error
    answer = app.session_state["ask_result"]
    assert not answer["refused"] and answer["metric_definition"]
    assert answer["sql_or_sources"] and answer["data_date"] == "2026-09-28"

    app.text_area(key="ask_question").set_value(
        "What will the weather be in Toronto tomorrow?"
    ).run()
    app.button(key="ask_submit").click().run()
    assert app.session_state["ask_result"]["refused"]
    assert any("Refused:" in item.value for item in app.warning)

    app.button(key="recommend_submit").click().run()
    assert not app.exception and not app.error
    proposal = app.session_state["recommendation"]
    assert proposal["customer_id"] == HERO_ID
    assert proposal["policy_checks"] and proposal["reasons"]
    assert any(row["decision_id"] == proposal["decision_id"]
               for row in latest_audit_rows(HERO_ID))

    app.text_input(key="reviewer_id").set_value("streamlit-smoke-test")
    app.text_area(key="review_reason").set_value(
        "Verify that human rejection is recorded without customer contact"
    )
    app.button(key="reject_button").click().run()
    assert not app.exception and not app.error, (
        [item.message for item in app.exception], [item.value for item in app.error]
    )
    assert any(row["decision_id"] == proposal["decision_id"]
               and row["disposition"] == "reject" for row in latest_audit_rows(HERO_ID))

    print({
        "hero_id": HERO_ID,
        "cases": len(customer["cases"]),
        "contacts": len(customer["contacts"]),
        "promises": len(customer["promises"]),
        "linked_sources": customer["identity"]["linked_source_count"],
        "ask_metric": "answered with SQL and definition",
        "ask_refusal": "shown",
        "recommendation_action": proposal["action"],
        "review": "rejection recorded and visible in audit",
    })


if __name__ == "__main__":
    main()
