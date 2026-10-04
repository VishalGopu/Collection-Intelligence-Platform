from app import ask
from src.insights.engine import AnswerCard


CUSTOMER = "G-39c6b287f70371cd9fc6"
CONTEXT = {"golden_customer_id": CUSTOMER, "found": True, "case_ids": []}


def test_explicit_this_customer_scope_maps_simple_count(monkeypatch):
    called = {}

    class FakeEngine:
        def __init__(self, root):
            self.connection = type("Connection", (), {"close": lambda self: None})()

        def answer(self, question, *, scope=None):
            called.update(question=question, scope=scope)
            return AnswerCard("AD-HOC", question, "open_cases\n1", "SELECT 1 AS open_cases",
                              mode="scoped_sql", scope=f"selected golden customer {scope}")

    monkeypatch.setattr(ask, "InsightEngine", FakeEngine)
    result = ask.answer("How many open cases are there?", golden_customer_id=CUSTOMER,
                        scope_requested=True, customer_context=CONTEXT)
    assert called == {"question": "How many open cases does this customer have?",
                      "scope": CUSTOMER}
    assert result["scope"] == "selected golden customer"
    assert result["question"] == "How many open cases are there?"


def test_explicit_this_customer_scope_refuses_unsupported_question(monkeypatch):
    monkeypatch.setattr(ask, "InsightEngine", lambda root: (_ for _ in ()).throw(
        AssertionError("Unsupported question must not enter the global engine")))
    result = ask.answer("How many open cases are 90 days past due?",
                        golden_customer_id=CUSTOMER, scope_requested=True,
                        customer_context=CONTEXT)
    assert result["refused"]
    assert "customer-scoped route" in result["answer"]
