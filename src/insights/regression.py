"""One-command real-data Layer 2 benchmark regression."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path

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


def run(dataset_root: Path, output_dir: Path, questions_path: Path | None = None) -> dict:
    started = time.monotonic()
    engine = InsightEngine(dataset_root)
    answers_path = output_dir / ("custom_answers.csv" if questions_path else "dev_answers.csv")
    if questions_path is None:
        cards = engine.run_benchmark(answers_path, split="dev")
    else:
        with questions_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        cards = [engine.answer(row["question_text"], row.get("question_id") or None) for row in rows]
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
        "api_calls": getattr(engine.llm_planner, "api_calls", 0),
        "cache_hits": getattr(engine.llm_planner, "cache_hits", 0),
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "regression_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("maple_data/maple_collections_release"))
    parser.add_argument("--output-dir", type=Path, default=Path("local_artifacts/insights/regression"))
    parser.add_argument("--questions", type=Path, help="Optional CSV with question_id and question_text")
    args = parser.parse_args()
    report = run(args.dataset_root, args.output_dir, args.questions)
    print(json.dumps(report, indent=2))
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
