"""Run with python -m src.decisioning.cli from the repository root."""

import argparse
from datetime import datetime
import json
from pathlib import Path

from .engine import DEMO_AS_OF, RecommendationEngine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('maple_data/maple_collections_release'))
    parser.add_argument('--c360-dir', type=Path, default=Path('local_artifacts/c360'))
    parser.add_argument('--audit-path', type=Path, default=Path('local_artifacts/decisioning/audit.sqlite'))
    sub = parser.add_subparsers(dest='command', required=True)
    recommend = sub.add_parser('recommend')
    recommend.add_argument('customer_id')
    recommend.add_argument('--as-of', type=datetime.fromisoformat, default=DEMO_AS_OF)
    for name in ('approve', 'modify', 'reject'):
        review = sub.add_parser(name)
        review.add_argument('decision_id')
        review.add_argument('--reviewer', required=True)
        review.add_argument('--reason', required=True)
        if name == 'modify':
            review.add_argument('--action', required=True)
    args = parser.parse_args()
    engine = RecommendationEngine(args.data_dir, args.c360_dir, audit_path=args.audit_path)
    try:
        if args.command == 'recommend':
            result = engine.recommend(args.customer_id, as_of=args.as_of)
        elif args.command == 'modify':
            result = engine.modify(args.decision_id, args.reviewer, args.action, args.reason)
        else:
            result = getattr(engine, args.command)(args.decision_id, args.reviewer, args.reason)
        print(json.dumps(result, indent=2))
    finally:
        engine.close()


if __name__ == '__main__':
    main()
