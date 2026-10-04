"""Safe app adapter for the existing Layer 2 answer card API."""

from __future__ import annotations

import re
import inspect
from dataclasses import asdict
from pathlib import Path

from app.customer import C360, DATASET, load_customer
from src.insights.engine import InsightEngine, SNAPSHOT_DATE


CASE_ID = re.compile(r"\bCS-\d{4}-\d+\b", re.IGNORECASE)
GOLDEN_ID_IN_QUESTION = re.compile(r"\bG-[0-9a-f]{20}\b", re.IGNORECASE)
CUSTOMER_SCOPE = re.compile(
    r"\b(this customer|selected customer|this person's|this person|their cases|"
    r"their promises|their contacts|for this golden|for customer G-[0-9a-f]+)\b",
    re.IGNORECASE,
)


def _refusal(question: str, message: str) -> dict:
    return {
        "question": question, "answer": message, "sql_or_sources": "customer-scope guardrail",
        "refused": True, "mode": "refusal", "data_date": SNAPSHOT_DATE,
        "metric_definition": None, "scope": "selected golden customer",
    }


def answer(
    question: str, *, golden_customer_id: str | None = None,
    dataset_root: Path = DATASET, c360_root: Path = C360,
    customer_context: dict | None = None,
) -> dict:
    """Answer general questions and case questions verified against the selected C360 ID.

    Pass the selected golden ID as Layer 2 scope when its answer API supports it.
    Until then, global metrics stay labelled global and customer wording refuses.
    """
    question = question.strip()
    if not question:
        raise ValueError("Enter a question")
    mentioned_ids = {"G-" + match[2:].lower() for match in GOLDEN_ID_IN_QUESTION.findall(question)}
    if len(mentioned_ids) > 1:
        return _refusal(question, "Ask about one golden customer at a time.")
    if mentioned_ids:
        mentioned_id = next(iter(mentioned_ids))
        if golden_customer_id is not None and golden_customer_id != mentioned_id:
            return _refusal(question, "The customer ID in the question does not match the selected scope.")
        golden_customer_id = mentioned_id
    context = None
    if golden_customer_id is not None:
        context = customer_context or load_customer(golden_customer_id, dataset_root, c360_root)
        if context["golden_customer_id"] != golden_customer_id:
            raise ValueError("Selected customer context does not match the requested golden ID")
        if not context["found"]:
            raise ValueError("Select a published golden customer first")
    case_ids = set(CASE_ID.findall(question))
    allowed_cases = {str(case_id).upper() for case_id in context["case_ids"]} if context else set()
    if golden_customer_id and case_ids and not {case_id.upper() for case_id in case_ids} <= allowed_cases:
        return _refusal(question, "That case is not linked to the selected golden customer.")
    customer_scoped = bool(CUSTOMER_SCOPE.search(question) or
                           (golden_customer_id and golden_customer_id.casefold() in question.casefold()))
    parameters = inspect.signature(InsightEngine.answer).parameters
    if golden_customer_id and customer_scoped and "scope" not in parameters and "golden_customer_id" not in parameters:
        return _refusal(
            question,
            "Customer-scoped Ask is waiting for Layer 2's golden-ID scope API. "
            "General Collections and linked-case questions are available now.",
        )
    engine = InsightEngine(dataset_root)
    try:
        if golden_customer_id and "scope" in parameters:
            card = engine.answer(question, scope=golden_customer_id)
        elif golden_customer_id and "golden_customer_id" in parameters:
            card = engine.answer(question, golden_customer_id=golden_customer_id)
        else:
            card = engine.answer(question)
    finally:
        engine.connection.close()
    result = asdict(card)
    result["data_date"] = result.pop("as_of_date")
    result["scope"] = ("selected golden customer" if result.get("scope", "").startswith("selected golden customer")
                       else "global Collections")
    return result
