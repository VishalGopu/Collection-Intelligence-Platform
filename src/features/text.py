"""Shared point-in-time text feature definition for training and live scoring.

Text annotations are precomputed into a separate cache. A missing annotation is
unknown, never evidence of no hardship. These context fields are not inputs to
the repayment model or action ranker and cannot alone authorize adverse action.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json


DELAY_REASONS = frozenset({'reduced_income', 'payroll_timing', 'forgot', 'bank_error',
                           'travel', 'dispute', 'refuses', 'other'})
HARDSHIP_VALUES = frozenset({'none', 'possible', 'clear'})
SCHEMA_VERSION = 'task-a-text-v1'


def normalize_annotation(annotation: dict) -> dict:
    hardship = annotation.get('hardship_signal')
    delay = annotation.get('stated_delay_reason')
    if hardship not in HARDSHIP_VALUES or delay not in DELAY_REASONS | {None}:
        raise ValueError('Text annotation outside the approved taxonomy')
    return {'hardship_signal': hardship, 'stated_delay_reason': delay}


def features_at(events: list[dict], cutoff: datetime, annotations: dict[str, dict]) -> dict:
    """Use the latest annotated note or completed call strictly before cutoff."""
    eligible = [event for event in events if event['event_ts'] < cutoff and
                (not event['event_id'].startswith('transcript:') or
                 event['event_ts'].date() < cutoff.date()) and
                event['event_id'] in annotations]
    if not eligible:
        return {'hardship_signal': None, 'stated_delay_reason': None,
                'text_source_id': None, 'text_source_ts': None}
    chosen = max(eligible, key=lambda row: (row['event_ts'], row['event_id']))
    values = normalize_annotation(annotations[chosen['event_id']])
    return {**values, 'text_source_id': chosen['event_id'],
            'text_source_ts': chosen['event_ts'].isoformat()}


def load_cache(path: Path = Path('local_artifacts/decisioning/text_annotations.json')) -> dict[str, dict]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Text annotation cache schema mismatch')
    return {key: normalize_annotation(value) for key, value in payload['annotations'].items()}
