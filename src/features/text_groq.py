"""Independent Groq batch extractor; no dependency on Layer 2 or its cache.

Run only during the agreed API window. Keep .env and text_annotations.json local.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, time
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
from time import sleep
from zoneinfo import ZoneInfo

from .text import DELAY_REASONS, SCHEMA_VERSION, normalize_annotation


ENDPOINT = 'https://api.groq.com/openai/v1/chat/completions'
DEFAULT_CACHE = Path('local_artifacts/decisioning/text_annotations.json')


def groq_key() -> str:
    key = os.environ.get('GROQ_API_KEY')
    if key:
        return key
    for path in (Path('.env'), Path('../.env')):
        if path.is_file():
            for line in path.read_text(encoding='utf-8').splitlines():
                if line.strip().startswith('GROQ_API_KEY='):
                    return line.split('=', 1)[1].strip().strip('"\'')
    raise RuntimeError('GROQ_API_KEY is missing from environment and .env')


def extract_batch(items: list[dict], key: str, model: str = 'openai/gpt-oss-20b') -> dict[str, dict]:
    """Classify a bounded batch, returning only approved labels by source ID."""
    prompt = (
        'Return strict JSON {"items":[{"id":"...","hardship_signal":"none|possible|clear",'
        '"stated_delay_reason":"reduced_income|payroll_timing|forgot|bank_error|travel|dispute|refuses|other|null"}]}.'
        ' Label only an explicitly stated customer circumstance. Use none for no hardship evidence; '
        'null when no delay reason is stated. Ignore agent speculation and protected traits. '
        'Items: ' + json.dumps(items, ensure_ascii=False)
    )
    body = {'model': model, 'temperature': 0, 'response_format': {'type': 'json_object'},
            'messages': [{'role': 'user', 'content': prompt}]}
    with tempfile.TemporaryDirectory() as directory:
        request = Path(directory) / 'request.json'
        response = Path(directory) / 'response.json'
        request.write_text(json.dumps(body), encoding='utf-8')
        result = subprocess.run(['curl', '-sS', '-f', '--max-time', '90', ENDPOINT,
                                 '-H', f'Authorization: Bearer {key}',
                                 '-H', 'Content-Type: application/json',
                                 '--data-binary', '@' + str(request),
                                 '-o', str(response)], capture_output=True, text=True, timeout=100)
        if result.returncode:
            raise RuntimeError(f'Groq request failed (curl exit {result.returncode})')
        payload = json.loads(response.read_text(encoding='utf-8'))
    parsed = json.loads(payload['choices'][0]['message']['content'])
    expected = {item['id'] for item in items}
    output = {row['id']: normalize_annotation(row) for row in parsed['items']}
    if set(output) != expected:
        raise ValueError('Groq response omitted or duplicated batch IDs')
    return output


def annotate_batches(items: list[dict], cache_path: Path = DEFAULT_CACHE,
                     batch_size: int = 10, pause_seconds: float = 2.0) -> dict:
    if not 1 <= batch_size <= 20:
        raise ValueError('batch_size must be 1..20')
    key = groq_key()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.is_file() else {
        'schema_version': SCHEMA_VERSION, 'annotations': {}, 'text_hashes': {}}
    if cache['schema_version'] != SCHEMA_VERSION:
        raise ValueError('Text cache schema mismatch')
    pending = [item for item in items if cache['text_hashes'].get(item['id']) !=
               sha256(item['text'].encode('utf-8')).hexdigest()]
    zone = ZoneInfo('Asia/Kolkata')
    now = datetime.now(zone)
    deadline = datetime.combine(now.date(), time(18, 0), zone)
    # Conservative preflight so the last planned batch completes before 18:00.
    planned_batches = (len(pending) + batch_size - 1) // batch_size
    if now + timedelta(seconds=planned_batches * 20) >= deadline:
        raise RuntimeError('Text extraction cannot finish before 18:00 IST; run on an earlier window')
    for start in range(0, len(pending), batch_size):
        if datetime.now(zone) >= deadline - timedelta(minutes=2):
            raise RuntimeError('Stopping before the 18:00 IST shared API cutoff')
        batch = pending[start:start + batch_size]
        for attempt in range(3):
            try:
                result = extract_batch(batch, key)
                break
            except (RuntimeError, ValueError, KeyError, json.JSONDecodeError):
                if attempt == 2:
                    raise
                sleep(5 * (attempt + 1))
        for item in batch:
            cache['annotations'][item['id']] = result[item['id']]
            cache['text_hashes'][item['id']] = sha256(item['text'].encode('utf-8')).hexdigest()
        temporary = cache_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
        temporary.replace(cache_path)
        if start + batch_size < len(pending):
            sleep(pause_seconds)
    return {'requested': len(pending), 'cached': len(cache['annotations'])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('items_json', type=Path, help='JSON list of {id,text} records')
    parser.add_argument('--batch-size', type=int, default=10)
    args = parser.parse_args()
    print(annotate_batches(json.loads(args.items_json.read_text(encoding='utf-8')),
                           batch_size=args.batch_size))


if __name__ == '__main__':
    main()
