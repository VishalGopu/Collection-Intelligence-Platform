from datetime import datetime

import duckdb
import pytest

from src.decisioning.data import CUSTOMER_COLUMNS, CASE_COLUMNS, CONTACT_COLUMNS, ReleaseAdapter
from src.decisioning.engine import DEMO_AS_OF
from src.decisioning.policy import policy_checks
from src.features.contacts import PROTECTED_FIELDS, ROUTING_ONLY_FIELDS


@pytest.fixture
def adapter():
    instance = ReleaseAdapter.__new__(ReleaseAdapter)
    instance.has_c360 = True
    con = instance.connection = duckdb.connect()
    con.execute('''CREATE TABLE identity_crosswalk (
        source_system VARCHAR, source_customer_id VARCHAR, golden_customer_id VARCHAR,
        match_method VARCHAR, match_confidence DOUBLE, link_status VARCHAR, as_of_date DATE)''')
    con.execute('''INSERT INTO identity_crosswalk VALUES
        ('crm','0001','G-1','exact',1,'linked','2026-09-28'),
        ('collections','COL-1','G-1','exact',1,'linked','2026-09-28'),
        ('cards','CARD-REF-1','G-1','exact',1,'linked','2026-09-28'),
        ('core_banking','CORE-1','G-1','exact',1,'linked','2026-09-28'),
        ('crm','0002',NULL,'none',0,'review_pending','2026-09-28')''')
    con.execute('''CREATE TABLE golden_customers (
        golden_customer_id VARCHAR, as_of_date DATE, dq_status VARCHAR,
        consent_call BOOLEAN, consent_sms BOOLEAN, consent_email BOOLEAN,
        crm_customer_ids VARCHAR[], min_match_confidence DOUBLE, open_case_count INTEGER,
        max_current_dpd INTEGER, total_overdue_cad DOUBLE, hardship_flag BOOLEAN)''')
    con.execute("INSERT INTO golden_customers VALUES ('G-1','2026-09-28','passed',true,true,true,['0001'],1,1,30,100,false)")
    for table, columns in [('customers_state', CUSTOMER_COLUMNS), ('cases_state', CASE_COLUMNS)]:
        con.execute(f"CREATE TABLE {table} ({','.join(c + ' VARCHAR' for c in columns)})")
    profile = dict.fromkeys(CUSTOMER_COLUMNS, 'false')
    profile.update(crm_customer_id='0001', time_zone='America/Toronto',
        consent_call='true', consent_sms='true', consent_email='true', consent_push='true',
        app_push_enabled='true', customer_status='active',
        permitted_call_start_local='07:00', permitted_call_end_local='21:00')
    case = dict.fromkeys(CASE_COLUMNS, 'false')
    case.update(case_id='CASE-1', coll_customer_ref='COL-1', case_status='open',
                contact_cap_7d='3', dispute_status='', primary_product='card', current_dpd='30', case_open_date='2026-08-01')
    con.execute(f"INSERT INTO customers_state VALUES ({','.join('?' for _ in CUSTOMER_COLUMNS)})", list(profile.values()))
    con.execute(f"INSERT INTO cases_state VALUES ({','.join('?' for _ in CASE_COLUMNS)})", list(case.values()))
    con.execute('''CREATE TABLE contact_evidence (
        contact_id VARCHAR, crm_customer_id VARCHAR, case_id VARCHAR, direction VARCHAR,
        channel VARCHAR, contact_ts_utc TIMESTAMP, contact_hour_local INTEGER,
        rpc_flag BOOLEAN, contact_cost_cad DOUBLE)''')
    con.execute('''CREATE TABLE support_events (
        crm_customer_id VARCHAR, case_id VARCHAR, contact_ts_utc TIMESTAMP,
        hardship_mentioned_flag BOOLEAN, vulnerability_disclosed_flag BOOLEAN,
        cease_request_flag BOOLEAN, sms_opt_out_flag BOOLEAN, email_unsubscribe_flag BOOLEAN)''')
    con.execute('''CREATE TABLE external_holds (
        bank_subject_ref VARCHAR, pull_date VARCHAR, fraud_alert_flag VARCHAR,
        deceased_indicator VARCHAR, bankruptcy_on_file_flag VARCHAR, consumer_proposal_on_file_flag VARCHAR)''')
    con.execute('CREATE TABLE card_holds (src_customer_ref VARCHAR, fraud_block_flag VARCHAR)')
    con.execute('''CREATE TABLE agents_state (agent_id VARCHAR, status VARCHAR, skill_hardship VARCHAR,
        vulnerable_customer_certified VARCHAR, current_case_load VARCHAR, max_concurrent_cases VARCHAR)''')
    con.execute("INSERT INTO agents_state VALUES ('AG-1','active','true','true','1','20')")
    yield instance
    instance.close()


def test_adapter_preserves_leading_zero_id_and_linked_customer(adapter):
    context = adapter.context('0001', DEMO_AS_OF)
    assert context.customer_id == 'G-1'
    assert context.crm_ids == ['0001']
    assert context.case_ids == ['CASE-1']
    assert policy_checks(context)['call']['allowed']


def test_golden_id_resolves_the_same_linked_crm_record(adapter):
    by_crm = adapter.context('0001', DEMO_AS_OF)
    by_golden = adapter.context('G-1', DEMO_AS_OF)
    assert by_golden.customer_id == by_crm.customer_id
    assert by_golden.crm_ids == ['0001']
    assert by_golden.case_ids == by_crm.case_ids


def test_unapproved_identity_cannot_recommend(adapter):
    with pytest.raises(ValueError, match='approved C360 link'):
        adapter.context('0002', DEMO_AS_OF)


@pytest.mark.parametrize('sql', [
    "UPDATE customers_state SET vulnerability_flag='true'",
    "UPDATE cases_state SET vulnerable_customer_flag='true'",
    "INSERT INTO support_events VALUES ('0001','CASE-1','2026-09-27',false,true,false,false,false)",
])
def test_all_three_vulnerability_sources_are_routing_only(adapter, sql):
    adapter.connection.execute(sql)
    context = adapter.context('0001', DEMO_AS_OF)
    assert context.specialist_safeguard
    assert context.specialist_agent_id == 'AG-1'
    checks = policy_checks(context)
    assert checks['specialist_review']['allowed']
    assert not any(checks[a]['allowed'] for a in ('call','sms','email','push','payment_plan_discussion'))


def test_future_support_event_is_not_consumed(adapter):
    adapter.connection.execute("INSERT INTO support_events VALUES ('0001','CASE-1','2026-09-29',true,true,true,true,true)")
    context = adapter.context('0001', DEMO_AS_OF)
    assert not context.specialist_safeguard
    assert not context.hardship
    assert not context.cease_contact
    assert context.consent['sms']


def test_conflicting_consent_blocks_channel(adapter):
    adapter.connection.execute("INSERT INTO customers_state SELECT * FROM customers_state")
    adapter.connection.execute("UPDATE customers_state SET consent_sms='false' WHERE rowid=1")
    assert not policy_checks(adapter.context('0001', DEMO_AS_OF))['sms']['allowed']


def test_missing_safety_status_fails_closed(adapter):
    adapter.connection.execute('UPDATE cases_state SET complaint_flag=NULL')
    assert not policy_checks(adapter.context('0001', DEMO_AS_OF))['call']['allowed']


def test_card_fraud_alert_uses_approved_link(adapter):
    adapter.connection.execute("INSERT INTO card_holds VALUES ('CARD-REF-1','true')")
    assert 'fraud_review_hold' in policy_checks(adapter.context('0001', DEMO_AS_OF))['call']['reasons']


def test_current_snapshot_cannot_be_used_as_historical_state(adapter):
    with pytest.raises(ValueError, match='frozen'):
        adapter.context('0001', datetime.fromisoformat('2026-09-01T16:00:00+00:00'))


def test_protected_inputs_not_selected_and_ranking_projection_has_no_safeguards():
    assert not set(CUSTOMER_COLUMNS + CASE_COLUMNS + CONTACT_COLUMNS) & PROTECTED_FIELDS
    assert not set(CONTACT_COLUMNS) & ROUTING_ONLY_FIELDS


def test_contract_registration_rejects_duplicate_source_key(adapter, tmp_path):
    adapter.connection.execute("INSERT INTO identity_crosswalk SELECT * FROM identity_crosswalk WHERE source_system='crm' AND source_customer_id='0001'")
    adapter.c360_dir = tmp_path
    for name in ('identity_crosswalk','golden_customers'):
        adapter.connection.execute(f"COPY {name} TO ? (FORMAT PARQUET)", [str(tmp_path / (name + '.parquet'))])
    # Registration normally installs views into a connection without these fixture tables.
    adapter.connection.close()
    adapter.connection = duckdb.connect()
    with pytest.raises(ValueError, match='identity contract'):
        adapter._register_contract()
