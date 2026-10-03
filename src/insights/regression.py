"""One-command real-data Layer 2 benchmark regression."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from .reference_sql import REFERENCE_SQL, compare_rows

from .engine import InsightEngine


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "before", "by",
    "for", "from", "in", "is", "it", "of", "on", "or", "should", "the",
    "their", "to", "was", "with",
}


def normalize(value: str) -> list[str]:
    return [token.strip(".") for token in re.findall(r"[a-z0-9.]+", value.casefold()) if token.strip(".") not in STOP_WORDS]


def compare_answer(actual: str, expected: str, refused: bool) -> tuple[bool, str]:
    if expected.casefold().startswith("refuse:"):
        return (refused, "expected refusal" if refused else "expected refusal but answer was returned")
    if refused:
        return False, "unexpected refusal"
    if "\n" in expected and "," in expected.splitlines()[0]:
        if actual.strip() == expected.strip():
            return True, "exact table match"
        return False, "table output differs from published development answer"
    expected_tokens = set(normalize(expected))
    actual_tokens = set(normalize(actual))
    numbers = {token for token in expected_tokens if re.fullmatch(r"\d+(?:\.\d+)?", token)}
    if not numbers.issubset(actual_tokens):
        return False, f"missing expected numeric facts: {sorted(numbers - actual_tokens)}"
    coverage = len(expected_tokens & actual_tokens) / max(1, len(expected_tokens))
    if coverage < 0.55:
        return False, f"text fact coverage too low: {coverage:.0%}"
    return True, f"text fact coverage {coverage:.0%}"


def read_questions(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return []
    if rows[0][:2] == ["question_id", "question_text"]:
        return [dict(zip(rows[0], row)) for row in rows[1:]]
    if any(len(row) < 2 for row in rows):
        raise ValueError(f"Expected ID and question text in {path}")
    return [{"question_id": row[0], "question_text": row[1]} for row in rows]


def run(dataset_root: Path, output_dir: Path, questions_path: Path | None = None, workload_60: bool = False,
        additional_questions: Path | None = None, no_llm_cache: bool = False) -> dict:
    started = time.monotonic()
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_database = output_dir.parent / "regression" / "query_cache.duckdb" if workload_60 else output_dir / "query_cache.duckdb"
    cache_database.parent.mkdir(parents=True, exist_ok=True)
    engine = InsightEngine(dataset_root, cache_database=cache_database)
    if no_llm_cache and engine.llm_planner is not None:
        engine.llm_planner.cache_enabled = False
    setup_seconds = time.monotonic() - started
    answers_path = output_dir / ("custom_answers.csv" if questions_path else "dev_answers.csv")
    profiles = []
    if questions_path is None and not workload_60:
        cards = engine.run_benchmark(answers_path, split="dev")
    else:
        source = questions_path or Path("tests/insights/new_questions.csv")
        rows = read_questions(source)
        if additional_questions:
            rows.extend(read_questions(additional_questions))
            ids = [row["question_id"] for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError("Question IDs must be unique across both CSV files")
        if workload_60:
            with (dataset_root / "data" / "benchmark_questions.csv").open(newline="", encoding="utf-8") as handle:
                released = list(csv.DictReader(handle))
            rows.extend({"question_id": "PERF-" + row["question_id"], "question_text": row["question_text"]} for row in released)
            rows.append({"question_id": "PERF-060", "question_text": "How many open collections cases are in each queue?"})
            if len(rows) != 60:
                raise ValueError(f"Expected 60 workload questions, got {len(rows)}")
        cards = []
        for row in rows:
            question_started = time.monotonic()
            before_api = getattr(engine.llm_planner, "api_seconds", 0.0)
            before_calls = getattr(engine.llm_planner, "api_calls", 0)
            before_hits = getattr(engine.llm_planner, "cache_hits", 0)
            before_retries = getattr(engine.llm_planner, "retry_count", 0)
            before_rate_limits = getattr(engine.llm_planner, "rate_limit_count", 0)
            before_retry_wait = getattr(engine.llm_planner, "retry_wait_seconds", 0.0)
            before_rate_wait = getattr(engine.llm_planner, "rate_limit_wait_seconds", 0.0)
            before_query = engine.query_seconds
            card = engine.answer(row["question_text"], row.get("question_id") or None)
            cards.append(card)
            print(f"{len(cards)}/{len(rows)} {card.question_id}: {card.mode}", flush=True)
            elapsed = time.monotonic() - question_started
            api_time = getattr(engine.llm_planner, "api_seconds", 0.0) - before_api
            query_time = engine.query_seconds - before_query
            profiles.append({
                "question_id": card.question_id,
                "elapsed_seconds": round(elapsed, 3),
                "api_seconds": round(api_time, 3),
                "duckdb_seconds": round(query_time, 3),
                "other_seconds": round(max(0.0, elapsed - api_time - query_time), 3),
                "api_calls": getattr(engine.llm_planner, "api_calls", 0) - before_calls,
                "cache_hits": getattr(engine.llm_planner, "cache_hits", 0) - before_hits,
                "retries": getattr(engine.llm_planner, "retry_count", 0) - before_retries,
                "rate_limits": getattr(engine.llm_planner, "rate_limit_count", 0) - before_rate_limits,
                "retry_wait_seconds": round(getattr(engine.llm_planner, "retry_wait_seconds", 0.0) - before_retry_wait, 3),
                "rate_limit_wait_seconds": round(getattr(engine.llm_planner, "rate_limit_wait_seconds", 0.0) - before_rate_wait, 3),
            })
        answers_path.parent.mkdir(parents=True, exist_ok=True)
        with answers_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["question_id", "answer", "sql_or_sources", "refused"])
            writer.writeheader()
            writer.writerows(card.benchmark_row() for card in cards)
    gold_path = dataset_root / "labels" / "benchmark_dev_answers.csv"
    with gold_path.open(newline="", encoding="utf-8") as handle:
        gold = {row["question_id"]: row for row in csv.DictReader(handle)}
    results = []
    for card in cards:
        expected = gold.get(card.question_id, {}).get("gold_answer", "")
        if expected:
            passed, reason = compare_answer(card.answer, expected, card.refused)
        else:
            passed = card.mode not in {"unable"}
            reason = "no gold answer; execution recorded" if passed else "question was not answered"
        results.append({"question_id": card.question_id, "passed": passed, "reason": reason, "mode": card.mode})
    report = {
        "passed": sum(item["passed"] for item in results),
        "total": len(results),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "setup_seconds": round(setup_seconds, 2),
        "api_seconds": round(getattr(engine.llm_planner, "api_seconds", 0.0), 2),
        "duckdb_seconds": round(engine.query_seconds, 2),
        "api_calls": getattr(engine.llm_planner, "api_calls", 0),
        "cache_hits": getattr(engine.llm_planner, "cache_hits", 0),
        "llm_cache_enabled": not no_llm_cache,
        "retry_count": getattr(engine.llm_planner, "retry_count", 0),
        "rate_limit_count": getattr(engine.llm_planner, "rate_limit_count", 0),
        "rate_limit_wait_count": getattr(engine.llm_planner, "rate_limit_wait_count", 0),
        "rate_limit_wait_seconds": round(getattr(engine.llm_planner, "rate_limit_wait_seconds", 0.0), 2),
        "retry_wait_seconds": round(getattr(engine.llm_planner, "retry_wait_seconds", 0.0), 2),
        "results": results,
        "profiles": profiles,
    }
    references = []
    for card in cards:
        if card.question_id not in REFERENCE_SQL:
            continue
        sql = REFERENCE_SQL[card.question_id]
        try:
            expected = engine.connection.execute(sql).fetchall()
            actual = engine.connection.execute(card.sql_or_sources).fetchall() if not card.refused else []
            matched = compare_rows(actual, expected)
            reason = "result rows match" if matched else "result rows differ"
        except Exception as exc:
            matched, reason = False, str(exc)[:160]
        references.append({"question_id": card.question_id, "matched": matched, "reason": reason, "reference_sql": sql})
    report["references"] = references
    report["reference_matches"] = sum(row["matched"] for row in references)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "regression_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if questions_path:
        def cell(value: str) -> str:
            return value.replace("|", "\\|").replace("\n", "<br>")
        lines = ["# Live question results", "", "| ID | Question | SQL or evidence | Answer | Status |", "| --- | --- | --- | --- | --- |"]
        for card in cards:
            status = "refused" if card.refused else ("no rows matched" if card.mode == "empty" else "answered")
            lines.append(f"| {card.question_id} | {cell(card.question)} | {cell(card.sql_or_sources)} | {cell(card.answer)} | {status} |")
        (output_dir / "question_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("maple_data/maple_collections_release"))
    parser.add_argument("--output-dir", type=Path, default=Path("local_artifacts/insights/regression"))
    parser.add_argument("--questions", type=Path, help="Optional CSV with question_id and question_text")
    parser.add_argument("--additional-questions", type=Path, help="Append a second CSV, preserving row order")
    parser.add_argument("--no-llm-cache", action="store_true", help="Disable LLM cache reads and writes")
    parser.add_argument("--workload-60", action="store_true", help="Run 24 new plus 35 released questions and one new queue question")
    args = parser.parse_args()
    report = run(args.dataset_root, args.output_dir, args.questions, args.workload_60,
                 args.additional_questions, args.no_llm_cache)
    print(json.dumps(report, indent=2))
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
