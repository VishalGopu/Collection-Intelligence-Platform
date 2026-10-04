"""Build offline rule annotations and measure them on public text labels.

Run after downloading the dataset: python -m src.features.text_rules
No API keys or network calls are used.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .text import SCHEMA_VERSION, extract_rules
from .text_data import DATA, evaluate_public, labelled_items


CACHE = Path('local_artifacts/decisioning/text_annotations.json')
REPORT = Path('src/decisioning/artifacts/text_public_evaluation.json')


def run(data_dir: Path = DATA, cache_path: Path = CACHE,
        report_path: Path = REPORT) -> dict:
    items, labels = labelled_items(data_dir)
    predictions = {item['id']: extract_rules(item['text']) for item in items}
    evaluation = evaluate_public(labels, predictions)
    annotations: dict[str, dict] = {}
    source_counts = {'note': 0, 'transcript': 0}
    positive_counts = {'note': 0, 'transcript': 0}

    with (data_dir/'data/agent_notes.csv').open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            source_counts['note'] += 1
            signal = extract_rules(row['note_text'] or '')
            if signal['hardship_signal'] != 'none' or signal['stated_delay_reason'] is not None:
                annotations['note:' + row['note_id']] = signal
                positive_counts['note'] += 1

    with (data_dir/'data/call_transcripts.csv').open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            source_counts['transcript'] += 1
            payload = json.loads((data_dir/'files'/row['file_path']).read_text(encoding='utf-8'))
            text = ' '.join(turn['text'] for turn in payload['turns']
                            if turn.get('speaker') == 'customer')
            signal = extract_rules(text)
            if signal['hardship_signal'] != 'none' or signal['stated_delay_reason'] is not None:
                annotations['transcript:' + row['transcript_id']] = signal
                positive_counts['transcript'] += 1

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        json.dump({'schema_version': SCHEMA_VERSION, 'method': 'deterministic rules',
                   'annotations': annotations}, handle, ensure_ascii=False)
    temporary.replace(cache_path)

    report = {
        'annotation_method': 'deterministic rules; no API',
        'status': 'complete',
        'schema_version': SCHEMA_VERSION,
        'source_records': source_counts,
        'cached_records_with_signal': positive_counts,
        'cache_policy': 'Sparse positive-signal cache; no annotation means unknown, not no hardship.',
        'public_evaluation': evaluation,
        'limitations': [
            'The public labels are synthetic and may be noisy; these metrics do not establish real-world accuracy.',
            'Public examples were inspected while writing the rules, so this is development-set measurement, not an independent test.',
            'Rules can miss paraphrases and languages not covered by the patterns.',
            'Signals are context only and cannot by themselves trigger adverse collection treatment.',
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
