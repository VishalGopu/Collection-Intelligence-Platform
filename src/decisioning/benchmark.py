"""Reproducible frozen-demo latency sample for the Streamlit engine."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import platform
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
import warnings

from .engine import RecommendationEngine


def timed(call):
    start = perf_counter()
    call()
    return round((perf_counter() - start) * 1000, 3)


def run(output: Path = Path('src/decisioning/artifacts/latency_report.json')) -> dict:
    with TemporaryDirectory() as directory:
        start = perf_counter()
        engine = RecommendationEngine(audit_path=Path(directory) / 'benchmark_audit.sqlite')
        initialization_ms = round((perf_counter() - start) * 1000, 3)
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', message='LightGBM binary classifier with TreeExplainer')
                cold_recommend = timed(lambda: engine.recommend('AAA-4262'))
                warm_recommend = [timed(lambda: engine.recommend('AAA-4262')) for _ in range(5)]
                cold_worklist = timed(lambda: engine.worklist(20))
                warm_worklist = [timed(lambda: engine.worklist(20)) for _ in range(5)]
        finally:
            engine.close()
    report = {
        'measured_at_utc': datetime.now(timezone.utc).isoformat(),
        'platform': platform.platform(),
        'python': platform.python_version(),
        'units': 'milliseconds, wall-clock',
        'initialization_ms': initialization_ms,
        'recommend_AAA_4262': {'cold_ms': cold_recommend,
            'warm_calls_ms': warm_recommend, 'warm_median_ms': round(median(warm_recommend), 3)},
        'worklist_20': {'cold_ms': cold_worklist,
            'warm_calls_ms': warm_worklist, 'warm_median_ms': round(median(warm_worklist), 3)},
        'scope': 'One reused engine, frozen snapshot, local data and SQLite audit; timings vary by host.',
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
