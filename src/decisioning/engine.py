"""Policy-gated recommendation with observed channel evidence and a promise model."""

from __future__ import annotations

from datetime import datetime
from copy import deepcopy
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
        self._cache_frozen = not supplied_adapter
        self.adapter = adapter or ReleaseAdapter(Path(data_dir), Path(c360_dir), Path(cache_path))
        self.audit = AuditStore(Path(audit_path))
        model_path = Path(__file__).resolve().parent / 'artifacts/promise_kept_lightgbm.joblib'
        self.model = None
        if model_path.is_file() and not supplied_adapter:
            from .model import PromiseModel
            self.model = PromiseModel(model_path)
        self._model_cache = {}
        self._worklist_frame = None
        self._worklist_raw = None
        self._worklist_order = None
        self._worklist_output = []
        self._evidence_cache = {}
        self._context_cache = {}
        self._broken_cache = {}

    def recommend(self, customer_id: str, *, as_of: datetime = DEMO_AS_OF) -> dict:
        context_key = (customer_id, as_of.isoformat())
        if self._cache_frozen and context_key in self._context_cache:
            context = self._context_cache[context_key]
        else:
            context = self.adapter.context(customer_id, as_of)
            if self._cache_frozen:
                self._context_cache[context_key] = context
        checks = policy_checks(context)
        local = local_time(context)
        band = time_band(local.hour) if local else 'afternoon'
        evidence_key = (as_of.isoformat(), band)
        if evidence_key not in self._evidence_cache:
            self._evidence_cache[evidence_key] = channel_evidence(self.adapter.connection, as_of, band)
        evidence = self._evidence_cache[evidence_key]
        broken_key = (context.customer_id, as_of.isoformat())
        if self._cache_frozen and broken_key in self._broken_cache:
            broken = self._broken_cache[broken_key]
        else:
            broken = prior_broken_promises(self.adapter.connection, context.crm_ids, as_of)
            if self._cache_frozen:
                self._broken_cache[broken_key] = broken
        if checks['specialist_review']['allowed']:
            choices = [{'action': 'specialist_review', 'score': None, 'channel': None},
                       {'action': 'wait', 'score': None, 'channel': None}]
        else:
            choices = rank_actions(evidence, broken, checks)
        choice = choices[0]
        reason = explain(choice, broken)
        routing_reason = None
        if choice['action'] == 'specialist_review':
            trigger = context.routing_trigger or ('hardship_flag' if context.hardship else 'vulnerability_flag')
            routing_reason = f'{trigger} triggered mandatory specialist review; normal collection actions are suppressed.'
            reason = routing_reason
        model_result = None
        if self.model is not None and context.linked:
            score_key = (context.customer_id, as_of.isoformat())
            if score_key not in self._model_cache:
                features = self.adapter.model_features(context)
                self._model_cache[score_key] = self.model.score(features) if features else None
            model_result = self._model_cache[score_key]
            if model_result:
                from .model import reason_sentence
                model_sentence = reason_sentence(model_result['shap_reasons'], choice['action'])
                reason = (routing_reason + ' ' + model_sentence) if routing_reason else model_sentence
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
            'policy_checks': checks,
            'reasons': ([routing_reason, model_sentence] if routing_reason and model_result else [reason]),
            'alternatives': choices[1:],
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
        if hasattr(self.adapter, 'text_features'):
            text_features = self.adapter.text_features(context)
            result['text_features'] = text_features
            if text_features.get('text_source_id'):
                result['text_evidence'] = (
                    f"Rule signals from {text_features['text_source_id']} dated "
                    f"{text_features['text_source_ts']}: hardship "
                    f"{text_features['hardship_signal']}; stated delay "
                    f"{text_features['stated_delay_reason'] or 'not identified'}. "
                    'Context only; not used to choose or rank actions.'
                )
            else:
                result['text_evidence'] = 'No pre-scoring rule text signal was available.'
            result['limitations'].append(
                'Precomputed rule text signals are context only; they cannot alone trigger an adverse action.')
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
        if self._worklist_frame is None:
            con = self.adapter.connection
            frame = con.execute(f'''SELECT p.*, c.earlier_kept_rate,c.days_since_last_payroll,
            x.golden_customer_id FROM read_parquet({quote(base)}) p
            JOIN read_parquet({quote(candidates)}) c USING(ptp_id)
            JOIN identity_crosswalk x ON x.source_system='crm'
              AND x.link_status='linked' AND x.source_customer_id=p.crm_customer_id
            JOIN golden_customers g ON g.golden_customer_id=x.golden_customer_id
              AND g.dq_status='passed'
            WHERE p.promise_created_ts <= TIMESTAMP '2026-09-28 16:00:00'
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
            raw = frame[list(MODEL_COLUMNS)].astype(float)
            filled = self.model.imputer.transform(raw)
            risk = 1 - self.model.model.predict_proba(filled)[:, 1]
            self._worklist_frame = frame
            self._worklist_raw = raw
            self._worklist_order = np.argsort(-risk, kind='stable')
        frame, raw = self._worklist_frame, self._worklist_raw
        for index in self._worklist_order[len(self._worklist_output):limit]:
            row = frame.iloc[int(index)]
            values = {name: (None if np.isnan(raw.iloc[int(index)][name]) else
                             float(raw.iloc[int(index)][name])) for name in MODEL_COLUMNS}
            scored = self.model.score(values)
            self._worklist_output.append({
                'ptp_id': row.ptp_id, 'customer_id': row.golden_customer_id,
                'crm_customer_id': row.crm_customer_id, 'case_id': row.case_id,
                'promise_created_ts': row.promise_created_ts.isoformat(),
                'dpd_at_creation': values['dpd_at_creation'],
                'overdue_at_creation': values['overdue_at_creation'],
                'probability_break': round(1 - scored['probability'], 6),
                'shap_reasons': scored['shap_reasons'],
                'top_reason': scored['shap_reasons'][0]['label'],
                'model_version': scored['model_version'],
            })
        return deepcopy(self._worklist_output[:limit])

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
