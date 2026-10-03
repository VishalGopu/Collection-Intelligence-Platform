from dataclasses import replace
from datetime import datetime, timezone
import json
import sqlite3

import duckdb
import pytest

from src.decisioning.engine import RecommendationEngine
from src.decisioning.policy import DecisionContext, filter_actions, policy_checks
from src.decisioning.ranking import rank_actions


AS_OF = datetime(2026, 9, 28, 16, tzinfo=timezone.utc)


@pytest.fixture
def context():
    return DecisionContext('G-0001', ['0001'], ['CASE-1'], AS_OF, 'America/Toronto',
        consent={'call': True, 'sms': True, 'email': True, 'push': True}, holiday=False,
        specialist_agent_id='AG-1')


class FakeAdapter:
    def __init__(self, context):
        self.current = context
        self.connection = duckdb.connect()
        self.connection.execute('''CREATE TABLE contact_evidence (
            channel VARCHAR, direction VARCHAR, contact_ts_utc TIMESTAMP,
            contact_hour_local INTEGER, rpc_flag BOOLEAN, contact_cost_cad DOUBLE)''')
        self.connection.execute('''INSERT INTO contact_evidence VALUES
            ('call','outbound','2026-09-27 16:00',12,true,5),
            ('sms','outbound','2026-09-27 16:00',12,false,0.1)''')
        self.connection.execute('''CREATE TABLE promise_evidence (
            crm_customer_id VARCHAR, ptp_created_ts TIMESTAMP, status_ts TIMESTAMP, ptp_status VARCHAR)''')

    def context(self, customer_id, as_of):
        assert customer_id in ('0001', 'G-0001')
        return replace(self.current, as_of=as_of)

    def close(self):
        self.connection.close()


@pytest.fixture
def engine(context, tmp_path):
    instance = RecommendationEngine(adapter=FakeAdapter(context), audit_path=tmp_path / 'audit.sqlite')
    yield instance
    instance.close()


def test_forbidden_action_blocked_even_with_high_score(context):
    blocked = replace(context, consent={'call': False})
    assert filter_actions(blocked, [{'action': 'call', 'score': 1000000},
                                    {'action': 'wait', 'score': 0}]) == [{'action': 'wait', 'score': 0}]


@pytest.mark.parametrize('change,reason', [
    ({'cease_contact': True}, 'cease_communication'),
    ({'holds': ['insolvency_hold']}, 'insolvency_hold'),
    ({'holds': ['deceased_hold']}, 'deceased_hold'),
    ({'holds': ['fraud_review_hold']}, 'fraud_review_hold'),
    ({'holds': ['open_dispute']}, 'open_dispute'),
    ({'holds': ['complaint_review_hold']}, 'complaint_review_hold'),
    ({'time_zone': None}, 'customer_time_zone_unknown'),
    ({'holiday': None}, 'statutory_holiday_or_calendar_unknown'),
    ({'holiday': True}, 'statutory_holiday_or_calendar_unknown'),
    ({'call_attempts_7d': 3}, 'rolling_7_day_contact_cap'),
    ({'payment_reminders_7d': 3}, 'rolling_7_day_contact_cap'),
    ({'linked': False}, 'identity_not_approved'),
    ({'representative': True}, 'representative_contact_required'),
])
def test_policy_blocks_all_collection_actions(context, change, reason):
    checks = policy_checks(replace(context, **change))
    for action in ('call', 'sms', 'email', 'push', 'payment_plan_discussion'):
        assert not checks[action]['allowed']
        assert reason in checks[action]['reasons']


def test_local_time_and_sunday_boundary(context):
    checks = policy_checks(replace(context, as_of=datetime(2026, 9, 28, 1, tzinfo=timezone.utc)))
    assert 'sunday_contact_not_permitted' in checks['call']['reasons']
    checks = policy_checks(replace(context, as_of=datetime(2026, 9, 28, 2, tzinfo=timezone.utc),
                                  time_zone='America/Regina'))
    assert not checks['call']['allowed']


@pytest.mark.parametrize('support', ['hardship', 'specialist_safeguard'])
def test_hardship_or_safeguard_routes_to_specialist(engine, support):
    engine.adapter.current = replace(engine.adapter.current, **{support: True})
    recommendation = engine.recommend('0001')
    assert recommendation['action'] == 'specialist_review'
    assert recommendation['specialist_agent_id'] == 'AG-1'
    assert all(not recommendation['policy_checks'][a]['allowed'] for a in
               ('call', 'sms', 'email', 'push', 'payment_plan_discussion'))
    assert recommendation['reasons'][0].startswith(
        'hardship_flag' if support == 'hardship' else 'vulnerability_flag')


def test_golden_and_crm_ids_produce_the_same_recommendation(engine):
    by_golden = engine.recommend('G-0001')
    by_crm = engine.recommend('0001')
    assert by_golden['customer_id'] == by_crm['customer_id'] == 'G-0001'
    assert by_golden['crm_customer_ids'] == by_crm['crm_customer_ids'] == ['0001']
    assert by_golden['action'] == by_crm['action']


def test_insolvency_hold_precedes_hardship_route(engine):
    engine.adapter.current = replace(engine.adapter.current, hardship=True, holds=['insolvency_hold'])
    assert engine.recommend('0001')['action'] == 'wait'


@pytest.mark.parametrize('disposition', ['approve', 'modify', 'reject'])
def test_audit_row_written_after_review(engine, disposition):
    recommendation = engine.recommend('0001')
    assert recommendation['identity_mode'] == 'linked_c360'
    assert recommendation['probabilities']['promise_kept'] is None
    kwargs = {'decision_id': recommendation['decision_id'], 'reviewer': 'reviewer-1', 'reason': 'Fixture review'}
    if disposition == 'modify':
        kwargs['action'] = 'wait'
    event = getattr(engine, disposition)(**kwargs)
    row = engine.audit.connection.execute('SELECT reviewer,disposition,final_action FROM review_events').fetchone()
    assert row == ('reviewer-1', disposition, event['final_action'])
    assert row[2] is None if disposition == 'reject' else row[2] is not None
    stored = engine.audit.get(recommendation['decision_id'])
    assert stored['action'] == recommendation['action']


def test_review_rechecks_policy_and_cannot_modify_to_blocked_action(engine):
    recommendation = engine.recommend('0001')
    engine.adapter.current = replace(engine.adapter.current, cease_contact=True)
    with pytest.raises(ValueError, match='policy block'):
        engine.modify(recommendation['decision_id'], 'reviewer-1', 'call', 'Try forbidden call')
    assert engine.audit.connection.execute('SELECT count(*) FROM review_events').fetchone()[0] == 0


def test_audit_append_only_and_one_terminal_review(engine):
    decision = engine.recommend('0001')
    engine.reject(decision['decision_id'], 'reviewer-1', 'Reject')
    with pytest.raises(sqlite3.IntegrityError):
        engine.reject(decision['decision_id'], 'reviewer-2', 'Repeated review')
    with pytest.raises(sqlite3.IntegrityError, match='Append-only'):
        engine.audit.connection.execute('DELETE FROM review_events')


def test_missing_channel_evidence_falls_back_to_wait(context):
    evidence = {c: {'mean_contact_cost_cad': None, 'rpc_rate': None} for c in ('call','sms','email','push')}
    assert rank_actions(evidence, 0, policy_checks(context))[0]['action'] == 'wait'


def test_requires_named_reviewer_and_reason(engine):
    decision = engine.recommend('0001')
    with pytest.raises(ValueError, match='Reviewer and reason'):
        engine.approve(decision['decision_id'], '', '')


def test_prediction_and_audit_are_json_serializable(engine):
    decision = engine.recommend('0001')
    assert json.loads(json.dumps(decision)) == engine.audit.get(decision['decision_id'])
