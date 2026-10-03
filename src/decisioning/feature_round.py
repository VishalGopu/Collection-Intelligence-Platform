"""Compare a small candidate feature round on the fixed chronological holdout."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import duckdb
import lightgbm as lgb
import pandas as pd
from sklearn.impute import SimpleImputer

from src.features.candidates import CANDIDATES
from src.features.training import FEATURE_COLUMNS, quote
from .train import SPLIT, evaluate


def run(base_path: Path, candidate_path: Path, output_path: Path) -> dict:
    con = duckdb.connect()
    try:
        frame = con.execute(f'''SELECT base.*, candidates.days_since_last_contact,
            candidates.earlier_kept_rate,candidates.promise_amount_to_overdue,
            candidates.days_since_last_payroll
            FROM read_parquet({quote(base_path)}) base
            JOIN read_parquet({quote(candidate_path)}) candidates USING(ptp_id)
            ORDER BY base.promise_created_ts,base.ptp_id''').df()
    finally:
        con.close()
    frame['promise_created_ts'] = pd.to_datetime(frame['promise_created_ts'])
    frame['status_ts'] = pd.to_datetime(frame['status_ts'])
    train_mask = (frame.promise_created_ts < SPLIT) & (frame.status_ts < SPLIT)
    test_mask = frame.promise_created_ts >= SPLIT
    training = frame.loc[train_mask]
    testing = frame.loc[test_mask]
    variants = {'baseline': FEATURE_COLUMNS}
    for candidate in CANDIDATES:
        variants[f'plus_{candidate}'] = (*FEATURE_COLUMNS, candidate)
    variants['all_candidates'] = (*FEATURE_COLUMNS, *CANDIDATES)
    variants['without_card_utilisation'] = tuple(x for x in FEATURE_COLUMNS if x != 'card_utilisation')
    variants['without_bureau_score_change'] = tuple(x for x in FEATURE_COLUMNS if x != 'bureau_score_change')
    variants['selected_candidate'] = (*[x for x in FEATURE_COLUMNS if x != 'bureau_score_change'],
                                      'earlier_kept_rate', 'days_since_last_payroll')
    results = {}
    for name, columns in variants.items():
        x_train = training.loc[:, list(columns)].astype(float)
        x_test = testing.loc[:, list(columns)].astype(float)
        imputer = SimpleImputer(strategy='median')
        fit_train = imputer.fit_transform(x_train)
        fit_test = imputer.transform(x_test)
        model = lgb.LGBMClassifier(n_estimators=180, learning_rate=0.04,
                                   num_leaves=15, max_depth=5,min_child_samples=80,
                                   verbosity=-1,random_state=17,n_jobs=4)
        model.fit(fit_train,training.label_kept.astype(int))
        predictions = model.predict_proba(fit_test)[:,1]
        scored = evaluate(testing.label_kept.astype(int).to_numpy(),predictions)
        results[name] = {
            'features': columns, 'roc_auc': scored['roc_auc'],
            'pr_auc_broken': scored['pr_auc_broken'],
            'brier': scored['calibration']['brier'],
            'top_10_capture': scored['lift_by_decile']['capture']['top_10_percent']['share_of_all_broken'],
            'top_20_capture': scored['lift_by_decile']['capture']['top_20_percent']['share_of_all_broken'],
        }
    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'train_rows': len(training),'test_rows': len(testing),
        'candidate_missingness': {
            name: {'train': round(float(training[name].isna().mean()),6),
                   'test': round(float(testing[name].isna().mean()),6)}
            for name in CANDIDATES},
        'variants': results,
        'limits': [
            'Same time holdout used for feature selection; gains may be optimistic.',
            'Payroll uses employer_flag=Y only; other income and benefits are excluded.',
            'Promise amount / overdue ratio was rejected: its near-perfect synthetic-label association is implausible target leakage or generation artifact.',
            'Selected set omits bureau score change, which hurt the holdout; card utilisation stays.',
            'The holdout measures prediction, not treatment uplift.',
        ],
    }
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=Path('local_artifacts/features/promise_training.parquet'))
    parser.add_argument('--candidates',type=Path,default=Path('local_artifacts/features/promise_candidates.parquet'))
    parser.add_argument('--output',type=Path,default=Path('src/decisioning/artifacts/feature_round.json'))
    args = parser.parse_args()
    report = run(args.base,args.candidates,args.output)
    for name, values in report['variants'].items():
        print(name, values['roc_auc'], values['pr_auc_broken'], values['brier'],flush=True)


if __name__ == '__main__':
    main()
