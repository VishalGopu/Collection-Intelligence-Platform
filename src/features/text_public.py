"""Prepare, annotate and evaluate the 1,000 public labelled text records.

The `run` command makes Groq calls. Run it only before the agreed 18:00 IST
cutoff, with GROQ_API_KEY in .env or the environment. The evaluator is offline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .text import load_cache
from .text_data import labelled_items, evaluate_public
from .text_groq import annotate_batches


ITEMS = Path('local_artifacts/decisioning/text_public_items.json')
REPORT = Path('src/decisioning/artifacts/text_public_evaluation.json')


def prepare() -> dict:
    items, _ = labelled_items()
    ITEMS.parent.mkdir(parents=True, exist_ok=True)
    ITEMS.write_text(json.dumps(items, ensure_ascii=False), encoding='utf-8')
    return {'items': len(items), 'local_file': str(ITEMS)}


def evaluate() -> dict:
    _, labels = labelled_items()
    metrics = evaluate_public(labels, load_cache())
    report = {'annotation_method': 'Groq batch JSON extraction',
              'status': 'complete' if all(value['evaluated'] == 500 for value in metrics.values())
                        else 'pending_api_extraction',
              'no_result_means': 'No Groq prediction; precision and recall are not estimable.',
              'public_evaluation': metrics}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'run', 'evaluate'))
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare())
    elif args.action == 'run':
        if not ITEMS.is_file():
            prepare()
        print(annotate_batches(json.loads(ITEMS.read_text(encoding='utf-8'))))
        print(evaluate())
    else:
        print(evaluate())


if __name__ == '__main__':
    main()
