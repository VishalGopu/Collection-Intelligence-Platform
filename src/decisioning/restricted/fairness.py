"""Restricted, aggregate-only fairness check; protected fields never enter scoring.

Run: python -m src.decisioning.restricted.fairness
This module is deliberately outside the model, ranking and adapter imports.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import warnings

import duckdb

from src.decisioning import RecommendationEngine
from src.features.training import quote


def evaluate(max_customers: int = 120, output: Path = Path('src/decisioning/artifacts/fairness_evaluation.md')) -> str:
    if max_customers < 1:
        raise ValueError('max_customers must be positive')
    data = Path('maple_data/maple_collections_release/data/customers.csv')
    crosswalk = Path('local_artifacts/c360/identity_crosswalk.parquet')
    con = duckdb.connect()
    try:
        # Only this restricted script selects these two protected columns.
        sample = con.execute(f'''SELECT x.golden_customer_id,
            coalesce(nullif(c.gender_code,''),'unknown') AS gender_code,
            coalesce(nullif(c.citizenship_status,''),'unknown') AS citizenship_status
            FROM read_csv({quote(data)},header=true,all_varchar=true) c
            JOIN read_parquet({quote(crosswalk)}) x
              ON x.source_system='crm' AND x.link_status='linked'
             AND x.source_customer_id=c.crm_customer_id
            JOIN read_parquet({quote(Path('local_artifacts/features/open_promise_features.parquet'))}) p
              ON p.crm_customer_id=c.crm_customer_id
            QUALIFY row_number() OVER (PARTITION BY x.golden_customer_id ORDER BY p.ptp_id)=1
            ORDER BY hash(x.golden_customer_id) LIMIT ?''', [max_customers]).fetchall()
    finally:
        con.close()
    aggregates = defaultdict(lambda: {'n': 0, 'risk_sum': 0.0, 'actions': defaultdict(int)})
    with TemporaryDirectory() as directory:
        engine = RecommendationEngine(audit_path=Path(directory) / 'fairness_audit.sqlite')
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', message='LightGBM binary classifier with TreeExplainer')
                for golden_id, gender, citizenship in sample:
                    try:
                        decision = engine.recommend(golden_id)
                    except ValueError:
                        continue
                    risk = decision['probabilities']['promise_kept']
                    if risk is None:
                        continue
                    for field, group in (('gender_code', gender), ('citizenship_status', citizenship)):
                        row = aggregates[(field, group)]
                        row['n'] += 1
                        row['risk_sum'] += 1 - risk
                        row['actions'][decision['action']] += 1
        finally:
            engine.close()
    lines = [
        '# Restricted fairness evaluation', '',
        f'Deterministic sample: up to {max_customers} linked customers with an open promise '
        'from the frozen 2026-09-28 release. These are descriptive checks, not parity guarantees.',
        '',
        '**gender_code and citizenship_status are used only for this aggregate measurement. '
        'They are never model features, ranking inputs or explanations.**', '',
        '| Field | Group | N | Mean predicted break risk | Recommended action mix |',
        '| --- | --- | ---: | ---: | --- |',
    ]
    for (field, group), row in sorted(aggregates.items()):
        if row['n'] < 10:
            continue
        mix = ', '.join(f'{name}: {count/row["n"]:.1%}'
                        for name, count in sorted(row['actions'].items()))
        lines.append(f'| {field} | {group} | {row["n"]} | '
                     f'{row["risk_sum"]/row["n"]:.3f} | {mix} |')
    lines += ['', 'Groups with fewer than 10 sampled customers are suppressed. '
              'The sample is small, selected by existing open promises, and action mix '
              'reflects current policy/consent as well as model context. Differences are '
              'diagnostic only; no causal or production fairness claim is made.', '']
    report = '\n'.join(lines)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding='utf-8')
    return report


if __name__ == '__main__':
    print(evaluate())
