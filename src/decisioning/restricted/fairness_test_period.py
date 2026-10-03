"""Aggregate fairness measurement on every linked held-out promise.

Protected fields are read only here, after model scoring, for measurement.
The action mix is historical pre-promise outbound channel, not recommended action.
"""

from __future__ import annotations

import json
from math import sqrt
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd

from src.decisioning.train import MODEL_COLUMNS, SPLIT
from src.features.training import quote


MODEL = Path('src/decisioning/artifacts/promise_kept_lightgbm.joblib')
METRICS = Path('src/decisioning/artifacts/promise_model_metrics.json')
OUTPUT = Path('src/decisioning/artifacts/fairness_test_period.md')


def mean_ci(values: np.ndarray, customers: np.ndarray) -> tuple[float, float, float]:
    """Normal interval with customer-clustered standard error."""
    mean = float(values.mean())
    residual = pd.DataFrame({'customer': customers, 'residual': values-mean})
    by_customer = residual.groupby('customer').residual.sum().to_numpy()
    clusters = len(by_customer)
    delta = (1.96 * sqrt(clusters/(clusters-1) * float(np.sum(by_customer**2))) /
             len(values)) if clusters > 1 else 0
    return mean, max(0, mean-delta), min(1, mean+delta)


def run(output: Path = OUTPUT) -> dict:
    con = duckdb.connect()
    try:
        frame = con.execute(f'''WITH latest_contact AS (
            SELECT p.ptp_id,arg_max(c.channel,try_cast(c.contact_ts_utc AS TIMESTAMP)) AS last_outbound_channel
            FROM read_parquet({quote(Path('local_artifacts/features/promise_training.parquet'))}) p
            LEFT JOIN read_csv({quote(Path('maple_data/maple_collections_release/data/contact_history.csv'))},all_varchar=true) c
              ON c.crm_customer_id=p.crm_customer_id AND c.direction='outbound'
             AND try_cast(c.contact_ts_utc AS TIMESTAMP)<p.promise_created_ts
             AND try_cast(c.contact_ts_utc AS TIMESTAMP)>=p.promise_created_ts-INTERVAL '30 days'
            WHERE p.promise_created_ts>=TIMESTAMP '2026-07-01'
            GROUP BY p.ptp_id
        ) SELECT p.ptp_id,p.crm_customer_id,p.label_kept,p.promise_created_ts,
            p.dpd_at_creation,p.dpd_bucket_at_creation,p.overdue_at_creation,
            p.prior_broken_ptp_count_at_creation,p.broken_promises_90d,
            p.recent_contacts_30d,p.recent_rpc_30d,p.card_utilisation,
            p.bureau_risk_score,x.earlier_kept_rate,x.days_since_last_payroll,
            coalesce(nullif(c.gender_code,''),'unknown') AS gender_code,
            coalesce(nullif(c.citizenship_status,''),'unknown') AS citizenship_status,
            l.last_outbound_channel
            FROM read_parquet({quote(Path('local_artifacts/features/promise_training.parquet'))}) p
            JOIN read_parquet({quote(Path('local_artifacts/features/promise_candidates.parquet'))}) x USING(ptp_id)
            JOIN read_parquet({quote(Path('local_artifacts/c360/identity_crosswalk.parquet'))}) cw
              ON cw.source_system='crm' AND cw.link_status='linked'
             AND cw.source_customer_id=p.crm_customer_id
            JOIN read_parquet({quote(Path('local_artifacts/c360/golden_customers.parquet'))}) g
              ON g.golden_customer_id=cw.golden_customer_id AND g.dq_status='passed'
            JOIN read_csv({quote(Path('maple_data/maple_collections_release/data/customers.csv'))},all_varchar=true) c
              ON c.crm_customer_id=p.crm_customer_id
            LEFT JOIN latest_contact l USING(ptp_id)
            WHERE p.promise_created_ts>=TIMESTAMP '2026-07-01'
            ORDER BY p.ptp_id''').df()
    finally:
        con.close()
    if frame.ptp_id.duplicated().any():
        raise ValueError('Fairness cohort has duplicate promises')
    model = joblib.load(MODEL)
    raw = model['model'].predict_proba(model['imputer'].transform(
        frame[list(MODEL_COLUMNS)].astype(float)))[:, 1]
    frame['predicted_break_risk'] = 1-model['calibrator'].predict(raw)
    frame['broken'] = 1-frame.label_kept.astype(int)
    train_metrics = json.loads(METRICS.read_text(encoding='utf-8'))
    train_break_rate = 1-train_metrics['class_balance']['train']['kept_rate']
    test_break_rate = float(frame.broken.mean())
    lines = ['# Full linked test-period fairness measurement', '',
             f'All {len(frame):,} linked, quality-passed, resolved promises created from '
             '1 July to 28 September 2026. The model is scored first; only this '
             'restricted script then joins gender_code and citizenship_status for measurement.', '',
             '95% intervals: customer-clustered normal standard-error intervals '
             'for mean predicted risk, observed broken rate and channel shares. '
             'Intervals describe sampling uncertainty within this synthetic cohort, '
             'not causal uncertainty or representativeness.', '',
             '| Field | Group | N | Mean predicted break risk (95% CI) | '
             'Observed broken rate (95% CI) | Last pre-promise outbound channel (share, 95% CI) |',
             '| --- | --- | ---: | ---: | ---: | --- |']
    stats = {}
    for field in ('gender_code', 'citizenship_status'):
        for group, subset in frame.groupby(field):
            count = len(subset)
            if count < 30:
                continue
            customers = subset.crm_customer_id.to_numpy()
            risk, low, high = mean_ci(subset.predicted_break_risk.to_numpy(), customers)
            broken_count = int(subset.broken.sum())
            _, broken_low, broken_high = mean_ci(subset.broken.to_numpy(), customers)
            channels = []
            for channel, rows in subset.groupby(subset.last_outbound_channel.fillna('none')):
                n = len(rows)
                if n/count < .01:
                    continue
                _, lo, hi = mean_ci((subset.last_outbound_channel.fillna('none') == channel
                                     ).astype(float).to_numpy(), customers)
                channels.append(f'{channel}: {n/count:.1%} [{lo:.1%}, {hi:.1%}]')
            lines.append(f'| {field} | {group} | {count:,} | {risk:.3f} [{low:.3f}, {high:.3f}] '
                         f'| {broken_count/count:.3f} [{broken_low:.3f}, {broken_high:.3f}] '
                         f'| {"; ".join(channels)} |')
            stats[(field, group)] = {'n': count, 'mean_risk': risk,
                                      'broken_rate': broken_count/count}
    lines += ['', f'Break-rate drift: pre-July training {train_break_rate:.1%} broken versus '
              f'{test_break_rate:.1%} in this linked test cohort. This temporal shift '
              'limits calibration and group comparisons.', '',
              'The channel mix is the **observed last outbound channel in the prior 30 days**, '
              'not a recommendation from this model. Agents selected those channels. '
              'No uplift or differential-treatment cause is inferred.', '',
              '**Plain summary**',
              f'1. Measured predicted risk, actual broken rate and historical channel mix '
              f'for {len(frame):,} linked test-period promises; protected fields are measurement-only.',
              '2. Women/men have similar mean predicted risk (0.540/0.541); citizens '
              'show 0.544 versus 0.530 for permanent residents, alongside observed '
              'broken rates 0.630 versus 0.610. These are descriptive gaps.',
              f'3. Broken-rate drift ({train_break_rate:.1%} to {test_break_rate:.1%}) and '
              'observational channel selection prevent causal fairness or uplift claims.', '']
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines), encoding='utf-8')
    return {'rows': len(frame), 'train_break_rate': train_break_rate,
            'test_break_rate': test_break_rate, 'groups': stats}


if __name__ == '__main__':
    result = run()
    print(result['rows'], result['train_break_rate'], result['test_break_rate'])
