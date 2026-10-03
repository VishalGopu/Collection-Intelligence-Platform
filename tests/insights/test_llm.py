import io
import json
from urllib.error import HTTPError, URLError

from src.insights.llm import OpenAIResponsesPlanner


class FakeResponse:
    def __init__(self, payload: dict):
        self.body = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.body.read()


def response(sql: str) -> FakeResponse:
    plan = json.dumps({"sql": sql, "metric_id": None})
    return FakeResponse({"output_text": plan})


def test_response_cache_avoids_second_api_call(tmp_path) -> None:
    calls = []

    def opener(*args, **kwargs):
        calls.append((args, kwargs))
        return response("SELECT count(*) FROM collections_cases")

    planner = OpenAIResponsesPlanner(
        "test-key", "test-model", tmp_path / "cache.json", opener=opener
    )
    first = planner.plan("How many cases?", "collections_cases(case_id)")
    second = planner.plan("How many cases?", "collections_cases(case_id)")
    assert first == second
    assert len(calls) == 1
    assert planner.api_calls == 1
    assert planner.cache_hits == 1


def test_transient_failures_are_retried(tmp_path) -> None:
    attempts = []
    sleeps = []

    def opener(*args, **kwargs):
        attempts.append(1)
        if len(attempts) < 3:
            raise URLError("temporary")
        return response("SELECT count(*) FROM collections_cases")

    planner = OpenAIResponsesPlanner(
        "test-key", "test-model", tmp_path / "cache.json",
        max_attempts=3, opener=opener, sleeper=sleeps.append,
    )
    plan = planner.plan("How many cases?", "collections_cases(case_id)")
    assert plan.sql.startswith("SELECT")
    assert len(attempts) == 3
    assert len(sleeps) == 2


def test_exhausted_quota_does_not_retry(tmp_path) -> None:
    attempts = []

    def opener(*args, **kwargs):
        attempts.append(1)
        body = io.BytesIO(json.dumps({"error": {"code": "credit_balance_exhausted"}}).encode())
        raise HTTPError("https://api.openai.com/v1/responses", 429, "Too Many Requests", {}, body)

    planner = OpenAIResponsesPlanner(
        "test-key", "test-model", tmp_path / "cache.json",
        max_attempts=3, opener=opener, sleeper=lambda delay: None,
    )
    from src.insights.llm import PlannerError
    try:
        planner.plan("How many cases?", "collections_cases(case_id)")
    except PlannerError as exc:
        assert "credit_balance_exhausted" in str(exc)
    else:
        raise AssertionError("Expected quota error")
    assert len(attempts) == 1
