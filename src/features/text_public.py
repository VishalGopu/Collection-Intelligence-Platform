"""Offline rule extraction and public-label evaluation for text features."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .text import extract_rules
from .text_data import labelled_items, evaluate_public
from .text_rules import run as run_rules


ITEMS = Path('local_artifacts/decisioning/text_public_items.json')


def prepare() -> dict:
    items, _ = labelled_items()
    ITEMS.parent.mkdir(parents=True, exist_ok=True)
    ITEMS.write_text(json.dumps(items, ensure_ascii=False), encoding='utf-8')
    return {'items': len(items), 'local_file': str(ITEMS)}


def evaluate() -> dict:
    items, labels = labelled_items()
    metrics = evaluate_public(labels, {item['id']: extract_rules(item['text']) for item in items})
    report = {'annotation_method': 'deterministic rules; no API',
              'status': 'complete',
              'public_evaluation': metrics}
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'run', 'evaluate'))
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare())
    elif args.action == 'run':
        print(run_rules())
    else:
        print(evaluate())


if __name__ == '__main__':
    main()
