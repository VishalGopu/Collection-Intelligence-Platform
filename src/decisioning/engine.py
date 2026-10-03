"""Policy-gated recommendation with observed channel evidence and a promise model."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np

from src.features.contacts import channel_evidence, prior_broken_promises, time_band
from .audit import AuditStore
from .data import ReleaseAdapter
from .policy import local_time, policy_checks
from .ranking import WEIGHTS, explain, rank_actions


DEMO_AS_OF = datetime.fromisoformat("2026-09-28T16:00:00+00:00")


class RecommendationEngine:
    def __init__(self, data_dir=Path('maple_data/maple_collections_release'),
                 c360_dir=Path('local_artifacts/c360'),
                 cache_path=Path('local_artifacts/decisioning/source_cache.duckdb'),
                 audit_path=Path('local_artifacts/decisioning/audit.sqlite'), *, adapter=None):
        supplied_adapter = adapter is not None
        self.adapter = adapter or ReleaseAdapter(Path(data_dir), Path(c360_dir), Path(cache_path))
        self.audit = AuditStore(Path(audit_path))
        model_path = Path(__file__).resolve().parent / 'artifacts/promise_kept_lightgbm.joblib'
        self.model = None
        if model_path.is_file() and not supplied_adapter:
            from .model import PromiseModel
            self.model = PromiseModel(model_path)

    def recommend(self, customer_id: str, *, as_of: datetime = DEMO_AS_OF) -> dict:
        context = self.adapter.context(customer_id, as_of)
        checks = policy_checks(context)
        local = local_time(context)
        evidence = channel_evidence(self.adapter.connection, as_of,
                                    time_band(local.hour) if local else 'afternoon')
        broken = prior_broken_promises(self.adapter.connection, context.crm_ids, as_of)
        if checks['specialist_review']['allowed']:
            choices = [{'action': 'specialist_review', 'score': None, 'channel': None},
                       {'action': 'wait', 'score': None, 'channel': None}]
        else:
            choices = rank_actions(evidence, broken, checks)
        choice = choices[0]
        reason = explain(choice, broken)
        model_result = None
        if self.model is not None and context.linked:
            features = self.adapter.model_features(context)
            if features:
                model_result = self.model.score(features)
                from .model import reason_sentence
                reason = reason_sentence(model_result['shap_reasons'], choice['action'])
        if choice['action'] == 'wait':
            blocked = sorted({reason for c in checks.values() for reason in c['reasons']
                              if reason not in ('no_specialist_route_needed',)})
            if blocked:
                descriptions = {
                    'identity_not_approved': 'the customer identity needs review',
                    'no_open_case': 'there is no open collection case',
                    'insolvency_hold': 'an insolvency hold applies',
                    'deceased_hold': 'an estate hold applies',
                    'fraud_review_hold': 'fraud review is required',
                    'open_dispute': 'a dispute remains open',
                    'complaint_review_hold': 'a complaint needs review',
                    'cease_communication': 'a cease-communication request applies',
                    'channel_consent_missing_or_conflicting': 'channel consent is missing or conflicting',
                    'outside_permitted_local_hours': 'the current local time is outside the contact window',
                    'customer_time_zone_unknown': 'the customer time zone is unknown',
                    'statutory_holiday_or_calendar_unknown': 'the holiday calendar blocks contact',
                    'rolling_7_day_contact_cap': 'the contact limit has been reached',
                    'representative_contact_required': 'contact must go through an authorised representative',
                    'safety_status_unknown': 'a required safety status is unknown',
                    'inactive_or_unknown_profile': 'the profile is inactive or needs review',
                    'special_case_queue_review': 'the case requires its assigned specialist queue',
                    'contact_window_unknown': 'the permitted contact window is unknown',
                    'sunday_contact_not_permitted': 'Sunday contact is not permitted',
                    'specialist_route_required': 'internal specialist review is required',
                    'hold_or_identity_review_takes_precedence': 'a hold or identity review takes precedence',
                }
                reason += ' Policy checks: ' + '; '.join(descriptions.get(code, 'manual review is required')
                                                        for code in blocked) + '.'
        result = {
            'decision_id': str(uuid4()), 'customer_id': context.customer_id,
            'crm_customer_ids': context.crm_ids,
            'identity_mode': 'linked_c360' if context.linked else 'crm_bootstrap_review_only',
            'as_of': as_of.isoformat(), 'data_snapshot_date': '2026-09-28',
            'action': choice['action'], 'channel': choice['channel'],
            'score': choice['score'],
            'probabilities': {'promise_kept': None,
                'observed_rpc_by_channel': {c: r['rpc_rate'] for c, r in evidence.items()}},
            'policy_checks': checks, 'reasons': [reason], 'alternatives': choices[1:],
            'channel_evidence': evidence,
            'specialist_agent_id': context.specialist_agent_id if choice['action'] == 'specialist_review' else None,
            'shap_reasons': model_result['shap_reasons'] if model_result else [],
            'requires_human_review': True, 'status': 'pending_review',
            'scorer_version': 'explicit-rule-v1',
            'promise_model_version': model_result['model_version'] if model_result else None,
            'policy_version': 'maple-thin-v1',
            'scoring_assumptions': WEIGHTS,
            'limitations': [
                'Observational channel rates: agents chose channels; these are not causal effects.',
                'Channel scores are assumed utilities; the separate promise model does not estimate action uplift.',
                'Frozen 2026-09-28 snapshot; this is a demo, not a live action execution system.',
                'Global channel/time-band rates; missing RPC labels are excluded.',
                'The release records zero RPCs for digital channels in the demo band; this metric may be call-oriented.',
            ],
        }
        if model_result:
            result['probabilities']['promise_kept'] = model_result['probability']
            result['limitations'][1] = (
                'Promise-kept probability is observational and conditional on a promise; it is not action uplift.')
        self.audit.save(result)
        return result

    def worklist(self, limit: int = 20) -> list[dict]:
        """Linked open promises, highest predicted break risk first, at creation time."""
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise ValueError('limit must be an integer from 1 to 1000')
        if self.model is None or not self.adapter.has_c360:
            raise ValueError('A trained model and approved C360 crosswalk are required')
        from src.features.training import quote
        from .train import MODEL_COLUMNS
        base = Path('local_artifacts/features/open_promise_features.parquet')
        candidates = Path('local_artifacts/features/open_promise_candidates.parquet')
        if not base.is_file() or not candidates.is_file():
            raise FileNotFoundError('Build open promise features with src.features.training and src.features.candidates')
        con = self.adapter.connection
        frame = con.execute(f'''SELECT p.*, c.earlier_kept_rate,c.days_since_last_payroll,
            x.golden_customer_id FROM read_parquet({quote(base)}) p
            JOIN read_parquet({quote(candidates)}) c USING(ptp_id)
            JOIN identity_crosswalk x ON x.source_system='crm'
              AND x.link_status='linked' AND x.source_customer_id=p.crm_customer_id
            ORDER BY p.ptp_id''').df()
        if frame.empty:
            return []
        if frame.ptp_id.duplicated().any():
            raise ValueError('Open promise identity is ambiguous')
        source_dates = ['latest_contact_ts','latest_prior_broken_ts',
                        'card_snapshot_date','bureau_pull_date','bureau_previous_pull_date']
        for name in source_dates:
            if ((frame[name].notna()) &
                    (frame[name].astype('datetime64[ns]') >= frame.promise_created_ts.astype('datetime64[ns]'))).any():
                raise ValueError(f'Future {name} in open promise features')
        columns = list(MODEL_COLUMNS)
        raw = frame[columns].astype(float)
        filled = self.model.imputer.transform(raw)
        risk = 1 - self.model.model.predict_proba(filled)[:, 1]
        ranked = np.argsort(-risk, kind='stable')[:limit]
        output = []
        for index in ranked:
            row = frame.iloc[int(index)]
            values = {name: (None if np.isnan(raw.iloc[int(index)][name]) else
                             float(raw.iloc[int(index)][name])) for name in columns}
            scored = self.model.score(values)
            output.append({
                'ptp_id': row.ptp_id, 'customer_id': row.golden_customer_id,
                'crm_customer_id': row.crm_customer_id, 'case_id': row.case_id,
                'promise_created_ts': row.promise_created_ts.isoformat(),
                'probability_break': round(1 - scored['probability'], 6),
                'shap_reasons': scored['shap_reasons'],
                'top_reason': scored['shap_reasons'][0]['label'],
                'model_version': scored['model_version'],
            })
        return output

    def _review(self, decision_id, reviewer, reason, disposition, action=None):
        decision = self.audit.get(decision_id)
        # Revalidate the frozen source context rather than trusting stored flags.
        context = self.adapter.context(decision['customer_id'], datetime.fromisoformat(decision['as_of']))
        return self.audit.review(decision_id, reviewer, disposition, reason,
                                 action or decision['action'], policy_checks(context))

    def approve(self, decision_id: str, reviewer: str, reason: str):
        return self._review(decision_id, reviewer, reason, 'approve')

    def modify(self, decision_id: str, reviewer: str, action: str, reason: str):
        return self._review(decision_id, reviewer, reason, 'modify', action)

    def reject(self, decision_id: str, reviewer: str, reason: str):
        return self._review(decision_id, reviewer, reason, 'reject')

    def close(self):
        self.audit.close()
        self.adapter.close()
