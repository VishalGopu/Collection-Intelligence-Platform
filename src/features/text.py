"""Shared point-in-time text feature definition for training and live scoring.

Rule annotations are precomputed into a separate cache. A missing annotation is
unknown, never evidence of no hardship. These context fields are not inputs to
the repayment model or action ranker and cannot alone authorize adverse action.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re
import unicodedata


DELAY_REASONS = frozenset({'reduced_income', 'payroll_timing', 'forgot', 'bank_error',
                           'travel', 'dispute', 'refuses', 'other'})
HARDSHIP_VALUES = frozenset({'none', 'possible', 'clear'})
SCHEMA_VERSION = 'text-rules-v1'


def extract_rules(text: str) -> dict:
    """Conservative, inspectable signals from customer-authored text only."""
    plain = unicodedata.normalize('NFKD', text.casefold())
    plain = ''.join(char for char in plain if not unicodedata.combining(char))
    plain = re.sub(r'\s+', ' ', plain)
    clear = (
        r'\b(?:lost (?:my |the )?job|laid off|position eliminated|unemployed|'
        r'hours (?:at work )?(?:were )?reduced|shifts? (?:at work )?(?:were )?cut|'
        r'pay (?:got |was )?cut|income (?:dropped|reduced)|off work sick|'
        r'medical leave|can.t pay (?:the whole|that right now)|'
        r'not able to pay that right now|asked (?:if|about) (?:pmt|payment|hardship)|'
        r'asked if pmt can be reduced)\b'
    )
    possible = (
        r'\b(?:money is tight|budget (?:very |has been really )?tight|'
        r'budget very tight|things are hard|struggling (?:a bit|financially)|'
        r'financial(?:ly)? difficult|c.est serre|difficile financierement|'
        r'can.t afford|cannot afford|hardship options)\b'
    )
    hardship = ('clear' if re.search(clear, plain) else
                'possible' if re.search(possible, plain) else 'none')
    reason_rules = (
        ('dispute', r'\b(?:disput(?:e|es|ed)|charge(?:s)? aren.t mine|statement is wrong|'
         r'payment (?:was )?not applied|late fee|fraud|litige|releve.*errone)\b'),
        ('bank_error', r'\b(?:bank (?:transfer )?(?:error|problem)|problem with my bank transfer|'
         r'probleme bancaire|technical (?:issue|error)|transfer failed)\b'),
        ('travel', r'\b(?:travell?(?:ed|ing)?|away on (?:a )?trip|voyage)\b'),
        ('forgot', r'\b(?:forgot|forgotten|missed (?:the )?due date|oublie)\b'),
        ('reduced_income', r'\b(?:lost (?:my |the )?job|laid off|position eliminated|'
         r'unemployed|hours (?:at work )?(?:were )?reduced|shifts? (?:at work )?(?:were )?cut|'
         r'pay (?:got |was )?cut|income (?:dropped|reduced)|reduced hours)\b'),
        ('payroll_timing', r'\b(?:payday|pay day|next pay|after (?:my |the )?pay|'
         r'payroll|salary|paie|paiera apres)\b'),
        ('refuses', r'\b(?:refus(?:e|es|ed) to pay|not paying that|won.t pay)\b'),
        ('other', r'\b(?:sort it out|will try to pay|try to pay|can pay|i can pay|'
         r'je vais regler)\b'),
    )
    delay = next((reason for reason, pattern in reason_rules if re.search(pattern, plain)), None)
    return {'hardship_signal': hardship, 'stated_delay_reason': delay}


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
