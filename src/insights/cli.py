"""Command-line interface for Layer 2."""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import InsightEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask governed Maple Collections questions")
    parser.add_argument("--dataset-root", type=Path, default=Path("maple_data/maple_collections_release"))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--question")
    group.add_argument("--benchmark", type=Path)
    parser.add_argument("--split", choices=("dev", "test"))
    args = parser.parse_args()

    engine = InsightEngine(args.dataset_root)
    if args.question:
        card = engine.answer(args.question)
        print(card.answer)
        print(f"\nEvidence ({card.mode}):\n{card.sql_or_sources}")
        print(f"Refused: {str(card.refused).lower()}")
    else:
        cards = engine.run_benchmark(args.benchmark, args.split)
        print(f"Wrote {len(cards)} answers to {args.benchmark}")


if __name__ == "__main__":
    main()
