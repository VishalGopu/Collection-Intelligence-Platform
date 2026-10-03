"""Load the evaluated LightGBM model and report its actual SHAP factors."""

from __future__ import annotations

import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

from src.features.training import FEATURE_COLUMNS, model_columns


DEFAULT_MODEL = Path(__file__).resolve().parent / 'artifacts/promise_kept_lightgbm.joblib'
LABELS = {
    'dpd_at_creation': 'days past due',
    'dpd_bucket_at_creation': 'delinquency bucket',
    'overdue_at_creation': 'overdue balance',
    'prior_broken_ptp_count_at_creation': 'earlier broken promises',
    'broken_promises_90d': 'broken promises in the previous 90 days',
    'recent_contacts_30d': 'collection contacts in the previous 30 days',
    'recent_rpc_30d': 'right-party contacts in the previous 30 days',
    'card_utilisation': 'card utilisation in the last completed monthly snapshot',
    'bureau_risk_score': 'last earlier bureau risk score',
    'bureau_score_change': 'earlier bureau score change',
}


class PromiseModel:
    def __init__(self, path: Path = DEFAULT_MODEL):
        saved = joblib.load(path)
        self.columns = tuple(saved['columns'])
        if self.columns != FEATURE_COLUMNS:
            raise ValueError('Saved model feature contract differs from the active definition')
        model_columns(self.columns)
        self.version = saved['version']
        self.imputer = saved['imputer']
        self.model = saved['model']
        self.explainer = shap.TreeExplainer(self.model)

    def score(self, values: dict) -> dict:
        model_columns(values)
        if tuple(values) != self.columns:
            raise ValueError('Scoring row is missing or reorders a model feature')
        raw = np.array([[np.nan if values[key] is None else float(values[key])
                         for key in self.columns]], dtype=float)
        filled = self.imputer.transform(pd.DataFrame(raw, columns=self.columns))
        probability = float(self.model.predict_proba(filled)[0, 1])
        contributions = self.explainer.shap_values(filled)
        if isinstance(contributions, list):
            contributions = contributions[-1]
        contributions = np.asarray(contributions)
        if contributions.ndim == 3:
            contributions = contributions[:, :, -1]
        if contributions.shape != (1, len(self.columns)):
            raise ValueError(f'Unexpected SHAP shape: {contributions.shape}')
        ranked = sorted(enumerate(contributions[0]), key=lambda pair: -abs(pair[1]))[:3]
        factors = []
        for index, impact in ranked:
            if not math.isfinite(float(impact)):
                raise ValueError('Non-finite SHAP reason')
            feature = self.columns[index]
            factors.append({'feature': feature, 'label': LABELS[feature],
                            'value': None if np.isnan(raw[0, index]) else float(raw[0, index]),
                            'shap_log_odds': float(impact),
                            'direction': 'raises' if impact >= 0 else 'lowers'})
        if len(factors) != 3:
            raise ValueError('Expected three SHAP factors')
        # Tree SHAP values for this classifier explain the raw log-odds margin.
        expected = np.asarray(self.explainer.expected_value).reshape(-1)[-1]
        margin = float(self.model.predict(filled, raw_score=True)[0])
        if not np.isclose(float(expected) + float(np.sum(contributions[0])), margin, atol=1e-4):
            raise ValueError('SHAP factors do not reconcile to the model margin')
        return {'probability': probability, 'model_version': self.version,
                'shap_reasons': factors}


def reason_sentence(factors: list[dict], action: str) -> str:
    if len(factors) != 3 or any(row['feature'] not in FEATURE_COLUMNS for row in factors):
        raise ValueError('Only the actual three model factors may be explained')
    clauses = []
    for factor in factors:
        value = 'not recorded' if factor['value'] is None else f"{factor['value']:.2f}"
        clauses.append(f"{factor['label']} ({value}) {factor['direction']} the model's promise-keeping score")
    policy = ('Policy requires specialist review.' if action == 'specialist_review' else
              'Policy permits the proposed action.' if action != 'wait' else
              'Policy or missing evidence calls for waiting.')
    return policy + ' The three strongest model factors are ' + '; '.join(clauses) + '.'
