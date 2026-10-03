"""The app forwards C360 scope only when Layer 2 explicitly accepts it."""

from app import ask
from src.insights.engine import AnswerCard


GOLDEN_ID = "G-39c6b287f70371cd9fc6"
CONTEXT = {"golden_customer_id": GOLDEN_ID, "found": True, "case_ids": ["CS-2026-123"]}


class _Connection:
    def close(self) -> None:
        pass


def test_customer_wording_refuses_until_layer_two_supports_scope(monkeypatch) -> None:
    class UnscopedEngine:
        def __init__(self, root) -> None:
            raise AssertionError("Do not query global metrics for a customer-scoped question")

        def answer(self, question):
            raise AssertionError("Should not answer")

    monkeypatch.setattr(ask, "InsightEngine", UnscopedEngine)
    result = ask.answer("How many open cases does this customer have?",
                        golden_customer_id=GOLDEN_ID, customer_context=CONTEXT)
    assert result["refused"]
    assert "waiting for Layer 2" in result["answer"]


def test_selected_golden_id_is_forwarded_when_scope_api_arrives(monkeypatch) -> None:
    received = []

    class ScopedEngine:
        def __init__(self, root) -> None:
            self.connection = _Connection()

        def answer(self, question, *, scope=None):
            received.append(scope)
            return AnswerCard("AD-HOC", question, "One open case", "SELECT 1")

    monkeypatch.setattr(ask, "InsightEngine", ScopedEngine)
    result = ask.answer("How many open cases does this customer have?",
                        golden_customer_id=GOLDEN_ID, customer_context=CONTEXT)
    assert received == [GOLDEN_ID]
    assert result["answer"] == "One open case"
    assert result["scope"] == "selected golden customer"
