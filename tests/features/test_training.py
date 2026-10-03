from datetime import datetime

import duckdb
import pytest

from src.features.contacts import PROTECTED_FIELDS, ROUTING_ONLY_FIELDS
from src.features.training import AUDIT_DATES, FEATURE_COLUMNS, model_columns, validate_frame


def test_training_matrix_excludes_all_protected_and_route_only_inputs():
    assert set(FEATURE_COLUMNS).isdisjoint(PROTECTED_FIELDS | ROUTING_ONLY_FIELDS)
    model_columns(FEATURE_COLUMNS)
    for name in PROTECTED_FIELDS | ROUTING_ONLY_FIELDS:
        with pytest.raises(ValueError):
            model_columns((*FEATURE_COLUMNS, name))
    with pytest.raises(ValueError, match='Unapproved'):
        model_columns((*FEATURE_COLUMNS, 'ccb_deposit_amount'))


@pytest.fixture
def table():
    con = duckdb.connect()
    columns = ', '.join(f'{name} DOUBLE' for name in FEATURE_COLUMNS)
    audit = ', '.join(f'{name} TIMESTAMP' for name in AUDIT_DATES)
    con.execute(f'''CREATE TABLE training_table (
        ptp_id VARCHAR, promise_created_ts TIMESTAMP, status_ts TIMESTAMP,
        label_kept INTEGER, {columns}, {audit})''')
    values = ['PTP-1', datetime(2026, 6, 1), datetime(2026, 6, 15), 1]
    values += [1.0] * len(FEATURE_COLUMNS)
    values += [datetime(2026, 5, 15)] * len(AUDIT_DATES)
    con.execute(f"INSERT INTO training_table VALUES ({','.join('?' for _ in values)})", values)
    yield con
    con.close()


def test_no_future_feature_dates_in_training_table(table):
    assert validate_frame(table)['future_or_invalid_rows'] == 0
    for field in AUDIT_DATES:
        table.execute(f'UPDATE training_table SET {field}=?', [datetime(2026, 6, 1)])
        with pytest.raises(ValueError, match='time/label'):
            validate_frame(table)
        table.execute(f'UPDATE training_table SET {field}=?', [datetime(2026, 5, 15)])


def test_outcome_before_promise_is_invalid(table):
    table.execute("UPDATE training_table SET status_ts='2026-05-31'")
    with pytest.raises(ValueError, match='time/label'):
        validate_frame(table)


def test_duplicate_promise_id_is_invalid(table):
    table.execute('INSERT INTO training_table SELECT * FROM training_table')
    with pytest.raises(ValueError, match='uniqueness'):
        validate_frame(table)
