"""Rebuild committed thin-flow evidence using linked customers and real data.

Run python -m src.decisioning.demo. No messages or collection actions are sent.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from .engine import RecommendationEngine


def choose_customer(engine, specialist: bool):
    con = engine.adapter.connection
    if not engine.adapter.has_c360:
        raise ValueError('Run src/c360/build.py first; the demo requires link_status=linked')
    candidates = con.execute("""
        SELECT DISTINCT crm.source_customer_id
        FROM cases_state c JOIN identity_crosswalk cases
          ON cases.source_system='collections' AND cases.source_customer_id=c.coll_customer_ref
        JOIN identity_crosswalk crm ON crm.golden_customer_id=cases.golden_customer_id
          AND crm.source_system='crm' AND crm.link_status='linked'
        JOIN golden_customers g ON g.golden_customer_id=crm.golden_customer_id
        WHERE cases.link_status='linked' AND g.dq_status='passed' AND c.case_status='open'
          AND coalesce(try_cast(c.hardship_flag AS BOOLEAN),false)=?
          AND NOT coalesce(try_cast(c.insolvency_hold_flag AS BOOLEAN),true)
          AND NOT coalesce(try_cast(c.deceased_hold_flag AS BOOLEAN),true)
        ORDER BY crm.source_customer_id LIMIT 200
    """, [specialist]).fetchall()
    for (crm_id,) in candidates:
        recommendation = engine.recommend(crm_id)
        if (specialist and recommendation['action'] == 'specialist_review') or (
                not specialist and recommendation['action'] in ('call','sms','email','push','payment_plan_discussion')):
            return crm_id, recommendation
    raise RuntimeError('No eligible demo customer among 200 linked candidates')


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    engine = RecommendationEngine()
    try:
        normal_id, normal = choose_customer(engine, False)
        support_id, support = choose_customer(engine, True)
        reviews = [engine.approve(normal['decision_id'], 'demo-reviewer', 'Reviewed permitted channel and historical evidence')]
        modified = engine.recommend(normal_id)
        reviews.append(engine.modify(modified['decision_id'], 'demo-reviewer', 'wait', 'Reviewer chooses to defer contact'))
        rejected = engine.recommend(normal_id)
        reviews.append(engine.reject(rejected['decision_id'], 'demo-reviewer', 'Reviewer rejects proposed contact'))
        reviews.append(engine.approve(support['decision_id'], 'demo-reviewer', 'Approve internal specialist review'))
        decisions = [normal, modified, rejected, support]
        persisted = engine.audit.connection.execute("""SELECT count(*) FROM review_events
            WHERE decision_id IN (?,?,?,?)""", [d['decision_id'] for d in decisions]).fetchone()[0]
        assert persisted == 4
        assert all(d['identity_mode'] == 'linked_c360' for d in decisions)
        assert all(not support['policy_checks'][a]['allowed'] for a in
                   ('call','sms','email','push','payment_plan_discussion'))
        report = {
            'phase': 'thin end-to-end MVP', 'generated_at': datetime.now(timezone.utc).isoformat(),
            'data_snapshot_date': normal['data_snapshot_date'], 'prediction_as_of': normal['as_of'],
            'normal_demo_customer': {'crm_customer_id': normal_id, 'golden_customer_id': normal['customer_id'],
                                     'link_status': 'linked', 'action': normal['action'], 'score': normal['score']},
            'specialist_demo_customer': {'crm_customer_id': support_id, 'golden_customer_id': support['customer_id'],
                                         'link_status': 'linked', 'action': support['action'],
                                         'agent_id': support['specialist_agent_id']},
            'channel_evidence': normal['channel_evidence'], 'scoring_assumptions': normal['scoring_assumptions'],
            'checks': {'linked_identity_contract': 'passed', 'recommendation_persisted': 'passed',
                       'approve_modify_reject_audit': 'passed', 'specialist_suppresses_normal_actions': 'passed',
                       'persisted_review_count': persisted},
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'models': {'logistic_regression': 'pending', 'lightgbm': 'pending',
                       'historical_model_scores_comparison': 'pending', 'shap': 'pending'},
            'limitations': normal['limitations'],
        }
        (output_dir / 'thin_flow_metrics.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        (output_dir / 'audit_sample.json').write_text(json.dumps({'decisions': decisions, 'reviews': reviews}, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
        return report
    finally:
        engine.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('src/decisioning/artifacts'))
    run(parser.parse_args().output_dir)


if __name__ == '__main__':
    main()
