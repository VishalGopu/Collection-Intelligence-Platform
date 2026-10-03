"""Source projections and public-label evaluation for the shared text definition."""

from __future__ import annotations

from collections import defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path

import duckdb
import pandas as pd

from .text import features_at, load_cache
from .training import quote


DATA = Path('maple_data/maple_collections_release')


def source_index(data_dir: Path = DATA) -> dict[str, list[dict]]:
    """Read only identifiers and event timestamps, keeping customer links local."""
    con = duckdb.connect()
    try:
        rows = con.execute(f'''SELECT 'note:' || note_id AS event_id,
                crm_customer_id,try_cast(note_ts_utc AS TIMESTAMP) AS event_ts
            FROM read_csv({quote(data_dir/'data/agent_notes.csv')},all_varchar=true)
            WHERE note_ts_utc IS NOT NULL
            UNION ALL
            SELECT 'transcript:' || transcript_id,crm_customer_id,
                try_cast(call_end_ts AS TIMESTAMP)
            FROM read_csv({quote(data_dir/'data/call_transcripts.csv')},all_varchar=true)
            WHERE call_end_ts IS NOT NULL''').fetchall()
    finally:
        con.close()
    grouped = defaultdict(list)
    for event_id, crm_id, timestamp in rows:
        if crm_id and timestamp:
            grouped[crm_id].append({'event_id': event_id, 'event_ts': timestamp})
    return grouped


def labelled_items(data_dir: Path = DATA) -> tuple[list[dict], list[dict]]:
    """Return public texts and gold labels; labels never enter scoring features."""
    root = data_dir / 'labels'
    notes = {}
    with (data_dir/'data/agent_notes.csv').open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            notes[row['note_id']] = row['note_text'] or ''
    transcripts = {}
    with (data_dir/'data/call_transcripts.csv').open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            transcripts[row['transcript_id']] = row['file_path']
    items, labels = [], []
    for filename, prefix, lookup in (
        ('agent_notes_labels_public_500.csv', 'note:', notes),
        ('call_transcripts_labels_public_500.csv', 'transcript:', transcripts),
    ):
        with (root/filename).open(newline='', encoding='utf-8') as stream:
            for row in csv.DictReader(stream):
                source_id = row['note_id'] if prefix == 'note:' else row['transcript_id']
                if prefix == 'note:':
                    content = lookup[source_id]
                else:
                    payload = json.loads((data_dir/'files'/lookup[source_id]).read_text(encoding='utf-8'))
                    content = ' '.join(turn['text'] for turn in payload['turns']
                                       if turn.get('speaker') == 'customer')
                event_id = prefix + source_id
                items.append({'id': event_id, 'text': content[:1800]})
                labels.append({'id': event_id, 'source': prefix.rstrip(':'),
                               'hardship_signal': row['label_hardship'],
                               'stated_delay_reason': row['label_stated_delay_reason'] or None})
    return items, labels


def precision_recall(true: list[bool], predicted: list[bool]) -> dict:
    tp = sum(a and b for a, b in zip(true, predicted))
    fp = sum(not a and b for a, b in zip(true, predicted))
    fn = sum(a and not b for a, b in zip(true, predicted))
    return {'tp': tp, 'fp': fp, 'fn': fn,
            'precision': round(tp/(tp+fp), 4) if tp+fp else None,
            'recall': round(tp/(tp+fn), 4) if tp+fn else None}


def evaluate_public(labels: list[dict], annotations: dict[str, dict]) -> dict:
    output = {}
    for source in ('note', 'transcript'):
        matched = [(label, annotations[label['id']]) for label in labels
                   if label['source'] == source and label['id'] in annotations]
        output[source] = {'public_labels': 500, 'evaluated': len(matched),
            'hardship_clear_or_possible': precision_recall(
                [label['hardship_signal'] != 'none' for label, _ in matched],
                [value['hardship_signal'] != 'none' for _, value in matched]),
            'stated_delay_reason_present': precision_recall(
                [label['stated_delay_reason'] is not None for label, _ in matched],
                [value['stated_delay_reason'] is not None for _, value in matched]),
            'delay_reason_exact_accuracy': round(sum(
                label['stated_delay_reason'] == value['stated_delay_reason']
                for label, value in matched)/len(matched), 4) if matched else None}
    return output


def build_training_text(data_dir: Path = DATA,
                        output_path: Path = Path('local_artifacts/features/promise_text.parquet')) -> dict:
    annotations = load_cache()
    index = source_index(data_dir) if annotations else {}
    con = duckdb.connect()
    try:
        promises = con.execute(f'''SELECT ptp_id,crm_customer_id,promise_created_ts
            FROM read_parquet({quote(Path('local_artifacts/features/promise_training.parquet'))})
            UNION ALL SELECT ptp_id,crm_customer_id,promise_created_ts
            FROM read_parquet({quote(Path('local_artifacts/features/open_promise_features.parquet'))})''').fetchall()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        con.execute('CREATE TABLE text_features (ptp_id VARCHAR, hardship_signal VARCHAR, '
                    'stated_delay_reason VARCHAR, text_source_id VARCHAR, text_source_ts TIMESTAMP)')
        batch = []
        for ptp_id, crm_id, created in promises:
            values = features_at(index.get(crm_id, []), created, annotations)
            batch.append((ptp_id, values['hardship_signal'], values['stated_delay_reason'],
                          values['text_source_id'], values['text_source_ts']))
            if len(batch) == 10000:
                con.register('text_batch', pd.DataFrame(batch, columns=(
                    'ptp_id', 'hardship_signal', 'stated_delay_reason',
                    'text_source_id', 'text_source_ts')))
                con.execute('INSERT INTO text_features SELECT * FROM text_batch')
                con.unregister('text_batch')
                batch.clear()
        if batch:
            con.register('text_batch', pd.DataFrame(batch, columns=(
                'ptp_id', 'hardship_signal', 'stated_delay_reason',
                'text_source_id', 'text_source_ts')))
            con.execute('INSERT INTO text_features SELECT * FROM text_batch')
            con.unregister('text_batch')
        bad = con.execute(f'''SELECT count(*) FROM text_features t JOIN
            (SELECT ptp_id,promise_created_ts FROM read_parquet({quote(Path('local_artifacts/features/promise_training.parquet'))})
             UNION ALL SELECT ptp_id,promise_created_ts FROM read_parquet({quote(Path('local_artifacts/features/open_promise_features.parquet'))})) p
            USING(ptp_id) WHERE t.text_source_ts>=p.promise_created_ts''').fetchone()[0]
        if bad:
            raise ValueError(f'Future text feature: {bad}')
        con.execute(f'COPY text_features TO {quote(output_path)} (FORMAT PARQUET, COMPRESSION ZSTD)')
        return {'rows': len(promises), 'annotated_rows': con.execute(
            'SELECT count(*) FROM text_features WHERE text_source_id IS NOT NULL').fetchone()[0],
            'future_rows': bad}
    finally:
        con.close()


if __name__ == '__main__':
    items, labels = labelled_items()
    report = evaluate_public(labels, load_cache())
    print(json.dumps({'training': build_training_text(), 'public_evaluation': report}, indent=2))
