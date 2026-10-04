"""Write the official four-column answer CSV for a supplied questions CSV.

From the repository root:
    python -m src.insights.submission --questions questions.csv --output answers.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .engine import InsightEngine
from .regression import read_questions


OUTPUT_COLUMNS = ("question_id", "answer", "sql_or_sources", "refused")


def run(
    questions_path: Path,
    output_path: Path,
    dataset_root: Path = Path("maple_data/maple_collections_release"),
    *,
    no_llm_cache: bool = False,
) -> int:
    questions = read_questions(questions_path)
    ids = [row["question_id"] for row in questions]
    if not ids or any(not value or not row["question_text"].strip()
                      for value, row in zip(ids, questions)):
        raise ValueError("Questions CSV must contain nonempty question_id and question_text rows")
    if len(ids) != len(set(ids)):
        raise ValueError("Question IDs must be unique")

    engine = InsightEngine(dataset_root)
    try:
        if no_llm_cache and engine.llm_planner is not None:
            engine.llm_planner.cache_enabled = False
        cards = [engine.answer(row["question_text"], row["question_id"]) for row in questions]
        for card in cards:
            if not card.refused and not card.sql_or_sources.strip():
                raise ValueError(f"Answered question {card.question_id} has no SQL or sources")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(card.benchmark_row() for card in cards)
        temporary.replace(output_path)
        return len(cards)
    finally:
        engine.connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path,
                        default=Path("maple_data/maple_collections_release"))
    parser.add_argument("--no-llm-cache", action="store_true")
    args = parser.parse_args()
    count = run(args.questions, args.output, args.dataset_root,
                no_llm_cache=args.no_llm_cache)
    print(f"Wrote {count} official answers to {args.output}")


if __name__ == "__main__":
    main()
