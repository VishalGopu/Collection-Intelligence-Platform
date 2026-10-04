import io
import json
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request

from src.insights.llm import OpenAIResponsesPlanner
from src.insights.engine import InsightEngine


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


def test_groq_curl_files_are_accessible_to_child_process(monkeypatch) -> None:
    def fake_run(command, *, input, capture_output, timeout, check):
        config = input.decode()
        body_line = next(line for line in config.splitlines() if line.startswith("data-binary = "))
        body_path = json.loads(body_line.split(" = ", 1)[1])[1:]
        with open(body_path, "rb") as body:
            assert json.load(body) == {"test": True}
        with open(command[command.index("--dump-header") + 1], "wb") as headers:
            headers.write(b"HTTP/1.1 200 OK\r\n\r\n")
        return subprocess.CompletedProcess(command, 0, b'{"ok":true}\n200', b"")

    monkeypatch.setattr("src.insights.llm.subprocess.run", fake_run)
    request = Request("https://api.groq.com/openai/v1/chat/completions",
                      data=b'{"test":true}', headers={"Authorization": "Bearer test-key"})
    with OpenAIResponsesPlanner._curl_open(request, timeout=5) as result:
        assert json.loads(result.read()) == {"ok": True}


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


def test_cache_can_be_disabled_without_read_or_write(tmp_path) -> None:
    calls = []

    def opener(*args, **kwargs):
        calls.append(1)
        return response("SELECT count(*) FROM collections_cases")

    path = tmp_path / "cache.json"
    planner = OpenAIResponsesPlanner(
        "test-key", "test-model", cache_path=path, opener=opener, cache_enabled=False
    )
    planner.plan("How many cases?", "collections_cases(case_id)")
    planner.plan("How many cases?", "collections_cases(case_id)")
    assert len(calls) == 2
    assert planner.cache_hits == 0
    assert not path.exists()


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


def test_groq_rate_limit_uses_fallback_without_wait(tmp_path) -> None:
    models = []
    sleeps = []

    def opener(request, **kwargs):
        payload = json.loads(request.data)
        models.append(payload["model"])
        if payload["model"] == "primary":
            raise HTTPError("https://api.groq.com", 429, "rate limited", {"Retry-After": "2.5"}, io.BytesIO(b'{"error":{"code":"rate_limit_exceeded"}}'))
        return FakeResponse({"choices": [{"message": {"content": json.dumps({"sql": "SELECT count(*) FROM collections_cases", "metric_id": None})}}]})

    planner = OpenAIResponsesPlanner(
        "test-key", "primary", provider="groq", fallback_model="backup",
        cache_path=tmp_path / "cache.json", max_attempts=2, opener=opener, sleeper=sleeps.append,
    )
    assert planner.plan("How many cases?", "collections_cases(case_id)").sql.startswith("SELECT")
    assert models == ["primary", "backup"]
    assert sleeps == []
    assert planner.last_model == "backup"


def test_groq_retry_after_is_respected_without_backup(tmp_path) -> None:
    sleeps = []
    attempts = []

    def opener(request, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise HTTPError("https://api.groq.com", 429, "rate limited", {"Retry-After": "2.5"}, io.BytesIO(b'{"error":{"code":"rate_limit_exceeded"}}'))
        return FakeResponse({"choices": [{"message": {"content": json.dumps({"sql": "SELECT count(*) FROM collections_cases", "metric_id": None})}}]})

    planner = OpenAIResponsesPlanner(
        "test-key", "primary", provider="groq", cache_path=tmp_path / "cache.json",
        max_attempts=2, opener=opener, sleeper=sleeps.append,
    )
    assert planner.plan("How many cases?", "collections_cases(case_id)").sql.startswith("SELECT")
    assert sleeps == [2.5]


def test_gemini_request_uses_generate_content_and_json_response(tmp_path) -> None:
    requests = []

    def opener(request, **kwargs):
        requests.append(request)
        return FakeResponse({"candidates": [{"content": {"parts": [{
            "text": json.dumps({"sql": "SELECT count(*) FROM collections_cases", "metric_id": None})
        }]}}]})

    planner = OpenAIResponsesPlanner(
        "test-gemini-key", "gemini-flash-latest", provider="gemini",
        cache_path=tmp_path / "cache.json", opener=opener,
    )
    plan = planner.plan("How many cases?", "collections_cases(case_id)")
    assert plan.sql == "SELECT count(*) FROM collections_cases"
    assert planner.plan("How many cases?", "collections_cases(case_id)") == plan
    assert len(requests) == 1
    assert requests[0].full_url.endswith("/models/gemini-flash-latest:generateContent")
    assert requests[0].get_header("X-goog-api-key") == "test-gemini-key"
    assert requests[0].get_header("Authorization") is None
    body = json.loads(requests[0].data)
    assert body["contents"][0]["parts"][0]["text"].startswith("You are a read-only DuckDB SQL planner")
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "model" not in body


def test_provider_is_explicitly_selected_from_environment(monkeypatch) -> None:
    monkeypatch.setattr("src.insights.engine.load_dotenv", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    monkeypatch.setenv("GROQ_API_KEY", "groq-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    for provider, expected in (("gemini", "gemini-secret"),
                               ("groq", "groq-secret"),
                               ("openai", "openai-secret")):
        monkeypatch.setenv("INSIGHTS_LLM_PROVIDER", provider)
        planner = InsightEngine._planner_from_environment()
        assert planner.provider == provider
        assert planner.api_key == expected
