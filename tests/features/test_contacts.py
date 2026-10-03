from datetime import datetime, timezone

import duckdb
import pytest

from src.features.contacts import (
    PROTECTED_FIELDS, ROUTING_ONLY_FIELDS, RANKING_FIELDS,
    channel_evidence, check_feature_columns, prior_broken_promises,
)


AS_OF = datetime(2026, 9, 28, 16, tzinfo=timezone.utc)


@pytest.fixture
def connection():
    con = duckdb.connect()
    con.execute('''CREATE TABLE contact_evidence (
        channel VARCHAR, direction VARCHAR, contact_ts_utc TIMESTAMP,
        contact_hour_local INTEGER, rpc_flag BOOLEAN, contact_cost_cad DOUBLE)''')
    con.execute('''CREATE TABLE promise_evidence (
        crm_customer_id VARCHAR, ptp_created_ts TIMESTAMP, status_ts TIMESTAMP, ptp_status VARCHAR)''')
    yield con
    con.close()


def test_no_future_or_cutoff_contact_in_features(connection):
    connection.execute('''INSERT INTO contact_evidence VALUES
        ('call','outbound','2026-09-27 16:00',12,true,5),
        ('call','outbound','2026-09-28 16:00',12,false,99),
        ('call','outbound','2026-09-29 16:00',12,false,99),
        ('call','inbound','2026-09-27 16:00',12,false,99),
        ('call','outbound','2026-01-01 16:00',12,false,99),
        ('call','outbound','2026-09-27 16:00',9,false,99),
        ('call','outbound','2026-09-27 16:00',12,NULL,99)''')
    evidence = channel_evidence(connection, AS_OF, 'afternoon')['call']
    assert evidence['attempts'] == 1
    assert evidence['rpc_rate'] == 1
    assert evidence['mean_contact_cost_cad'] == 5
    assert datetime.fromisoformat(evidence['latest_source_ts']) < AS_OF.replace(tzinfo=None)


def test_later_promise_outcome_never_becomes_earlier_feature(connection):
    connection.execute('''INSERT INTO promise_evidence VALUES
        ('0001','2026-09-01','2026-09-10','broken'),
        ('0001','2026-09-01','2026-09-29','broken'),
        ('0001','2026-09-01','2026-09-28 16:00','broken'),
        ('0002','2026-09-01','2026-09-10','broken')''')
    assert prior_broken_promises(connection, ['0001'], AS_OF) == 1


@pytest.mark.parametrize('column', sorted(PROTECTED_FIELDS | ROUTING_ONLY_FIELDS))
def test_protected_and_routing_fields_rejected_from_feature_matrix(column):
    with pytest.raises(ValueError, match='Forbidden feature'):
        check_feature_columns([*RANKING_FIELDS, column])


def test_active_ranker_feature_columns_are_allowlisted():
    check_feature_columns(RANKING_FIELDS)
    assert not set(RANKING_FIELDS) & (PROTECTED_FIELDS | ROUTING_ONLY_FIELDS)


def test_naive_prediction_time_rejected(connection):
    with pytest.raises(ValueError, match='timezone'):
        channel_evidence(connection, datetime(2026, 9, 28), 'morning')
