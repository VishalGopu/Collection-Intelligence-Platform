"""Safe app adapter for the existing Layer 2 answer card API."""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path

from app.customer import C360, DATASET, load_customer
from src.insights.engine import InsightEngine, SNAPSHOT_DATE


CASE_ID = re.compile(r"\bCS-\d{4}-\d+\b", re.IGNORECASE)
CUSTOMER_SCOPE = re.compile(
    r"\b(this customer|selected customer|this person's|this person|their cases|"
    r"their promises|their contacts|for this golden|for customer G-[0-9a-f]+)\b",
    re.IGNORECASE,
)


def _refusal(question: str, message: str) -> dict:
    return {
        "question": question, "answer": message, "sql_or_sources": "customer-scope guardrail",
        "refused": True, "mode": "refusal", "data_date": SNAPSHOT_DATE,
        "metric_definition": None, "scope": "selected customer",
    }


def answer(
    question: str, *, golden_customer_id: str,
    dataset_root: Path = DATASET, c360_root: Path = C360,
    customer_context: dict | None = None,
) -> dict:
    """Answer general questions and case questions verified against the selected C360 ID.

    Current Layer 2 SQL metrics remain global. This adapter never labels them as
    customer-specific and refuses implicit customer-scoped wording.
    """
    question = question.strip()
    if not question:
        raise ValueError("Enter a question")
    context = customer_context or load_customer(golden_customer_id, dataset_root, c360_root)
    if context["golden_customer_id"] != golden_customer_id:
        raise ValueError("Selected customer context does not match the requested golden ID")
    if not context["found"]:
        raise ValueError("Select a published golden customer first")
    case_ids = set(CASE_ID.findall(question))
    allowed_cases = {str(case_id).upper() for case_id in context["case_ids"]}
    if case_ids and not {case_id.upper() for case_id in case_ids} <= allowed_cases:
        return _refusal(question, "That case is not linked to the selected golden customer.")
    if CUSTOMER_SCOPE.search(question) or golden_customer_id.casefold() in question.casefold():
        return _refusal(
            question,
            "Customer-scoped analytical questions are not connected to C360 yet. "
            "Ask a general Collections question or select a linked case question.",
        )
    engine = InsightEngine(dataset_root)
    try:
        card = engine.answer(question)
    finally:
        engine.connection.close()
    result = asdict(card)
    result["data_date"] = result.pop("as_of_date")
    result["scope"] = "selected linked case" if case_ids else "global Collections"
    return result
