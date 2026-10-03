"""Chronological promise-kept baseline and LightGBM evaluation.

Rebuild with ``python -m src.features.training`` followed by
``python -m src.decisioning.train``. The generated data stays ignored; the
small model and evaluation report are committed under artifacts/.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import duckdb
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             log_loss, roc_auc_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.features.training import FEATURE_COLUMNS, APPROVED_CANDIDATES, model_columns, quote, validate_frame


SPLIT = pd.Timestamp('2026-07-01')
MODEL_VERSION = 'promise-kept-v2'
MODEL_COLUMNS = tuple(column for column in FEATURE_COLUMNS if column != 'bureau_score_change') + APPROVED_CANDIDATES


def calibration(y, probability) -> dict:
    probability = np.asarray(probability, dtype=float)
    y = np.asarray(y, dtype=int)
    bins = []
    for i in range(10):
        selected = (probability >= i / 10) & (probability < (i + 1) / 10 if i < 9 else probability <= 1)
        if selected.any():
            bins.append({'range': [round(i / 10, 1), round((i + 1) / 10, 1)],
                         'count': int(selected.sum()),
                         'mean_predicted': round(float(probability[selected].mean()), 6),
                         'observed_kept': round(float(y[selected].mean()), 6)})
    ece = sum(row['count'] * abs(row['mean_predicted'] - row['observed_kept'])
              for row in bins) / len(y)
    return {'brier': round(float(brier_score_loss(y, probability)), 6),
            'expected_calibration_error': round(float(ece), 6), 'bins': bins}


def broken_risk_lift(y, kept_probability) -> dict:
    """Rank held-out promises by break risk; report actual broken capture."""
    labels = np.asarray(y, dtype=int)
    risk = 1 - np.asarray(kept_probability, dtype=float)
    order = np.argsort(-risk, kind='stable')
    broken = 1 - labels[order]
    ranked_risk = risk[order]
    total_broken = int(broken.sum())
    base_rate = float(broken.mean())
    deciles = []
    for index in range(10):
        start = index * len(broken) // 10
        end = (index + 1) * len(broken) // 10
        if start == end:
            continue
        segment = broken[start:end]
        count = len(segment)
        segment_broken = int(segment.sum())
        deciles.append({
            'risk_rank_decile': index + 1, 'rows': count,
            'mean_predicted_break_risk': round(float(ranked_risk[start:end].mean()), 6),
            'observed_break_rate': round(segment_broken / count, 6),
            'share_of_all_broken': round(segment_broken / total_broken, 6) if total_broken else None,
            'lift_vs_test_break_rate': round((segment_broken / count) / base_rate, 6) if base_rate else None,
        })
    captured = {}
    for share in (10, 20):
        size = (len(broken) * share + 99) // 100
        count = int(broken[:size].sum())
        captured[f'top_{share}_percent'] = {
            'rows': size, 'broken_promises': count,
            'share_of_all_broken': round(count / total_broken, 6) if total_broken else None,
            'lift_vs_test_break_rate': round((count / size) / base_rate, 6) if base_rate else None,
        }
    return {'riskiest_decile_first': deciles, 'capture': captured}


def evaluate(y, probability) -> dict:
    if len(y) == 0:
        return {'rows': 0, 'metrics': None}
    probability = np.clip(np.asarray(probability, dtype=float), 1e-7, 1 - 1e-7)
    result = {
        'rows': len(y), 'kept_rate': round(float(np.mean(y)), 6),
        'roc_auc': round(float(roc_auc_score(y, probability)), 6) if len(set(y)) == 2 else None,
        'average_precision': round(float(average_precision_score(y, probability)), 6),
        'pr_auc_broken': round(float(average_precision_score(1-np.asarray(y), 1-probability)), 6),
        'pr_auc_definition': 'average precision, positive class = broken promise',
        'log_loss': round(float(log_loss(y, probability)), 6),
        'calibration': calibration(y, probability),
    }
    result['reliability_table'] = result['calibration']['bins']
    result['lift_by_decile'] = broken_risk_lift(y, probability)
    return result


def compare_existing_scores(con, split: Path, data_dir: Path,
                            predictions: dict[str, tuple[float, float]]) -> dict:
    """Strict pre-promise scores only; filter false protected flag, never unknown."""
    source = quote(data_dir / 'data/model_scores.csv')
    con.execute(f'''CREATE OR REPLACE TEMP VIEW allowed_scores AS SELECT
        model_name, crm_customer_id, ptp_id,
        try_cast(score_ts AS TIMESTAMP) AS score_ts,
        try_cast(score AS DOUBLE) AS score
        FROM read_csv({source}, header=true, all_varchar=true)
        WHERE try_cast(uses_protected_attributes AS BOOLEAN)=false
          AND try_cast(score AS DOUBLE) BETWEEN 0 AND 1''')
    output = {}
    for model, join, orientation in (
        ('ptp_break', 's.ptp_id=t.ptp_id', '1 - score (break risk to kept)'),
        ('collections_risk', 's.crm_customer_id=t.crm_customer_id',
         '1 - score (different target; directional proxy only)'),
    ):
        # score_ts is an event timestamp, so a score created on the same day
        # but after the promise must never enter this comparison.
        query = f'''SELECT t.ptp_id,t.label_kept,
            arg_max(1-s.score, s.score_ts) AS kept_proxy
            FROM read_parquet({quote(split)}) t
            JOIN allowed_scores s ON {join} AND s.model_name=?
                AND s.score_ts<t.promise_created_ts
            WHERE t.promise_created_ts>=TIMESTAMP '2026-07-01'
              AND t.promise_created_ts<=TIMESTAMP '2026-09-28 23:59:59'
            GROUP BY t.ptp_id,t.label_kept'''
        rows = con.execute(query, [model]).fetchall()
        labels = [r[1] for r in rows]
        probabilities = [r[2] for r in rows]
        comparable = [r for r in rows if r[0] in predictions]
        output[model] = {'orientation': orientation, 'eligible_comparison': evaluate(labels, probabilities),
                         'same_rows_logistic': evaluate([r[1] for r in comparable],
                                                        [predictions[r[0]][0] for r in comparable]),
                         'same_rows_lightgbm': evaluate([r[1] for r in comparable],
                                                        [predictions[r[0]][1] for r in comparable]),
                         'cutoff_rule': 'score_ts < ptp_created_ts; uses_protected_attributes=false'}
    return output


def train(table_path: Path, output_dir: Path, data_dir: Path,
          candidate_path: Path = Path('local_artifacts/features/promise_candidates.parquet')) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute(f'CREATE VIEW training_table AS SELECT * FROM read_parquet({quote(table_path)})')
        checked = validate_frame(con)
        model_columns(FEATURE_COLUMNS)
        frame = con.execute(f'''SELECT base.*, candidates.earlier_kept_rate,
            candidates.days_since_last_payroll FROM training_table base
            JOIN read_parquet({quote(candidate_path)}) candidates USING(ptp_id)
            ORDER BY base.promise_created_ts,base.ptp_id''').df()
        if len(frame) != checked['rows']:
            raise ValueError('Candidate feature join lost or duplicated promise rows')
        frame['promise_created_ts'] = pd.to_datetime(frame['promise_created_ts'])
        frame['status_ts'] = pd.to_datetime(frame['status_ts'])
        train_mask = ((frame.promise_created_ts < SPLIT) & (frame.status_ts < SPLIT))
        test_mask = (frame.promise_created_ts >= SPLIT)
        training = frame.loc[train_mask]
        testing = frame.loc[test_mask]
        if len(training) == 0 or len(testing) == 0:
            raise ValueError('Chronological split produced an empty set')
        x_train = training.loc[:, list(MODEL_COLUMNS)].astype(float)
        x_test = testing.loc[:, list(MODEL_COLUMNS)].astype(float)
        y_train = training.label_kept.astype(int)
        y_test = testing.label_kept.astype(int)
        baseline = make_pipeline(SimpleImputer(strategy='median'), StandardScaler(),
                                 LogisticRegression(max_iter=400, random_state=17))
        baseline.fit(x_train, y_train)
        base_probability = baseline.predict_proba(x_test)[:, 1]
        imputer = SimpleImputer(strategy='median')
        filled_train = imputer.fit_transform(x_train)
        filled_test = imputer.transform(x_test)
        boosted = lgb.LGBMClassifier(n_estimators=180, learning_rate=0.04,
                                     num_leaves=15, max_depth=5, min_child_samples=80,
                                     verbosity=-1, random_state=17, n_jobs=4)
        boosted.fit(filled_train, y_train)
        boost_probability = boosted.predict_proba(filled_test)[:, 1]
        predictions = {ptp_id: (float(base_probability[i]), float(boost_probability[i]))
                       for i, ptp_id in enumerate(testing.ptp_id)}
        scores = compare_existing_scores(con, table_path, data_dir, predictions)
        report = {
            'model_version': MODEL_VERSION,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'label': '1=kept, 0=broken; open, cancelled and partially kept excluded',
            'data_snapshot_date': '2026-09-28',
            'split': {'training_promise_before': '2026-07-01',
                      'training_label_observed_before': '2026-07-01',
                      'test_promise_from': '2026-07-01',
                      'test_observation_ends': '2026-09-28',
                      'excluded_train_rows_with_late_outcome': int(((frame.promise_created_ts < SPLIT) &
                                                                      (frame.status_ts >= SPLIT)).sum())},
            'class_balance': {
                'train': {'rows': len(training), 'kept': int(y_train.sum()),
                          'broken': int((1-y_train).sum()), 'kept_rate': round(float(y_train.mean()), 6)},
                'test': {'rows': len(testing), 'kept': int(y_test.sum()),
                         'broken': int((1-y_test).sum()), 'kept_rate': round(float(y_test.mean()), 6)},
            },
            'features': list(MODEL_COLUMNS), 'training_validation': checked,
            'missingness': {column: {'train_fraction': round(float(x_train[column].isna().mean()), 6),
                                     'test_fraction': round(float(x_test[column].isna().mean()), 6)}
                            for column in MODEL_COLUMNS},
            'logistic_regression': evaluate(y_test, base_probability),
            'lightgbm': evaluate(y_test, boost_probability),
            'existing_model_scores': scores,
            'signal_assessment': (
                'Signal remains modest: held-out ROC AUC is around 0.68 and calibration is weak '
                'after the train/test kept-rate shift. Rank lift does not imply action uplift.'),
            'limitations': [
                'The backtest is observational and cannot establish treatment uplift.',
                'Current C360 identity links map historical bureau records; link provenance is from the later snapshot.',
                'Source event-time cutoffs do not prove complete historical ingestion availability.',
                'The promise-kept model predicts outcome after a promise; it does not estimate which channel causes repayment.',
                'Protected and routing-only attributes, deposits and transactions are excluded from the model matrix.',
                'Employer payroll uses employer_flag=Y; benefit/other-income rows are excluded. The same time holdout selected features, so measured gains may be optimistic.',
                'Promise amount/overdue was rejected after a near-perfect synthetic-label association; likely target leakage or data-generation artifact.',
            ],
        }
        artifact = {'version': MODEL_VERSION, 'columns': MODEL_COLUMNS,
                    'imputer': imputer, 'model': boosted}
        joblib.dump(artifact, output_dir / 'promise_kept_lightgbm.joblib', compress=3)
        (output_dir / 'promise_model_metrics.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        return report
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', type=Path, default=Path('local_artifacts/features/promise_training.parquet'))
    parser.add_argument('--output-dir', type=Path, default=Path('src/decisioning/artifacts'))
    parser.add_argument('--data-dir', type=Path, default=Path('maple_data/maple_collections_release'))
    parser.add_argument('--candidates', type=Path, default=Path('local_artifacts/features/promise_candidates.parquet'))
    args = parser.parse_args()
    print(json.dumps(train(args.table, args.output_dir, args.data_dir, args.candidates), indent=2))


if __name__ == '__main__':
    main()
