from pathlib import Path

import pytest

from src.decisioning.engine import RecommendationEngine


DATA = Path('maple_data/maple_collections_release')
C360 = Path('local_artifacts/c360')


@pytest.mark.skipif(not (DATA / 'data/customers.csv').is_file() or
                    not (C360 / 'identity_crosswalk.parquet').is_file(),
                    reason='Full Maple release and local C360 handoff required')
def test_linked_hero_golden_and_crm_ids_receive_same_model_and_policy(tmp_path):
    engine = RecommendationEngine(audit_path=tmp_path / 'hero_audit.sqlite')
    try:
        golden = engine.recommend('G-39c6b287f70371cd9fc6')
        crm = engine.recommend(golden['crm_customer_ids'][0])
        assert golden['customer_id'] == crm['customer_id']
        assert golden['action'] == crm['action'] == 'specialist_review'
        assert golden['reasons'][0].startswith(('collections_cases.hardship_flag',
               'contact_history.hardship_mentioned_flag', 'customers.vulnerability_flag',
               'collections_cases.vulnerable_customer_flag',
               'contact_history.vulnerability_disclosed_flag'))
        assert golden['promise_model_version'] == crm['promise_model_version'] == 'promise-kept-v3'
        assert len(golden['shap_reasons']) == len(crm['shap_reasons']) == 3
        assert golden['probabilities']['promise_kept'] == crm['probabilities']['promise_kept']
        assert all(not golden['policy_checks'][action]['allowed'] for action in
                   ('call','sms','email','push','payment_plan_discussion'))
        event = engine.approve(golden['decision_id'], 'integration-reviewer', 'Approve specialist handling')
        assert event['final_action'] == 'specialist_review'
        assert engine.audit.connection.execute('SELECT count(*) FROM review_events').fetchone()[0] == 1
    finally:
        engine.close()
