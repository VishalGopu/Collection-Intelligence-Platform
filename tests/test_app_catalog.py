from pathlib import Path

import duckdb
import pytest

from app.catalog import browse_customers
from app.customer import _path


def _catalog(tmp_path: Path) -> Path:
    con = duckdb.connect()
    try:
        con.execute(f"""COPY (
            SELECT * FROM (VALUES
              ('G-aaaaaaaaaaaaaaaaaaaa', 2, 90, 100.0, 'passed'),
              ('G-bbbbbbbbbbbbbbbbbbbb', 0, NULL, 0.0, 'passed'),
              ('G-cccccccccccccccccccc', 1, 60, 50.0, 'passed'),
              ('G-dddddddddddddddddddd', 3, 120, 200.0, 'passed')
            ) AS t(golden_customer_id, open_case_count, max_current_dpd,
                   total_overdue_cad, dq_status)
        ) TO {_path(tmp_path / 'golden_customers.parquet')} (FORMAT PARQUET)""")
        con.execute(f"""COPY (
            SELECT * FROM (VALUES
              ('G-aaaaaaaaaaaaaaaaaaaa', 'crm', 'linked'),
              ('G-bbbbbbbbbbbbbbbbbbbb', 'crm', 'linked'),
              ('G-cccccccccccccccccccc', 'crm', 'linked'),
              ('G-dddddddddddddddddddd', 'crm', 'review_pending')
            ) AS t(golden_customer_id, source_system, link_status)
        ) TO {_path(tmp_path / 'identity_crosswalk.parquet')} (FORMAT PARQUET)""")
        activity = duckdb.connect(str(tmp_path / "customer_page.duckdb"))
        try:
            activity.execute("""CREATE TABLE customer_activity AS SELECT * FROM (VALUES
                ('G-bbbbbbbbbbbbbbbbbbbb', 2, 1, 0),
                ('G-cccccccccccccccccccc', 3, 0, 1),
                ('G-dddddddddddddddddddd', 1, 1, 0)
            ) AS t(golden_customer_id, promise_count, broken_promise_count,
                   open_promise_count)""")
        finally:
            activity.close()
    finally:
        con.close()
    return tmp_path


def test_catalog_pages_cover_every_linked_customer_without_loading_all(tmp_path):
    root = _catalog(tmp_path)
    first = browse_customers(limit=2, c360_root=root)
    assert first['total'] == 3
    assert [row['golden_customer_id'] for row in first['rows']] == [
        'G-aaaaaaaaaaaaaaaaaaaa', 'G-bbbbbbbbbbbbbbbbbbbb']
    assert first['has_next']
    second = browse_customers(after_id=first['rows'][-1]['golden_customer_id'],
                              limit=2, c360_root=root)
    assert [row['golden_customer_id'] for row in second['rows']] == [
        'G-cccccccccccccccccccc']
    assert not second['has_next']


def test_catalog_search_and_open_case_filter_use_only_published_links(tmp_path):
    root = _catalog(tmp_path)
    assert [row['golden_customer_id'] for row in browse_customers(
        search='bbbb', c360_root=root)['rows']] == ['G-bbbbbbbbbbbbbbbbbbbb']
    assert [row['golden_customer_id'] for row in browse_customers(
        only_open_cases=True, c360_root=root)['rows']] == [
            'G-aaaaaaaaaaaaaaaaaaaa', 'G-cccccccccccccccccccc']
    assert browse_customers(search='zzzz', c360_root=root)['total'] == 0
    with pytest.raises(ValueError, match='Page size'):
        browse_customers(limit=101, c360_root=root)


def test_catalog_activity_filters_find_linked_customers_with_promises(tmp_path):
    root = _catalog(tmp_path)
    def ids(activity_filter):
        return [row['golden_customer_id'] for row in browse_customers(
            activity_filter=activity_filter, c360_root=root)['rows']]

    assert ids('open_cases') == ['G-aaaaaaaaaaaaaaaaaaaa', 'G-cccccccccccccccccccc']
    assert ids('any_promise') == ['G-bbbbbbbbbbbbbbbbbbbb', 'G-cccccccccccccccccccc']
    assert ids('broken_promise') == ['G-bbbbbbbbbbbbbbbbbbbb']
    assert ids('open_promise') == ['G-cccccccccccccccccccc']
    assert ids('open_cases_and_promises') == ['G-cccccccccccccccccccc']
    assert browse_customers(c360_root=root)['rows'][1]['promise_count'] == 2
