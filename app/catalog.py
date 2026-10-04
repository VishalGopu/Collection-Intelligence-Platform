"""Read-only, bounded browser over the published linked golden customers."""

from __future__ import annotations

from pathlib import Path

import duckdb

from app.customer import C360, _path
from app.prepare_customer_data import CACHE


PAGE_SIZE = 10
ACTIVITY_FILTERS = ("all", "open_cases", "any_promise", "broken_promise",
                    "open_promise", "open_cases_and_promises")


def browse_customers(
    search: str = "", *, after_id: str | None = None,
    only_open_cases: bool = False, limit: int = PAGE_SIZE,
    c360_root: Path = C360, activity_filter: str = "all",
) -> dict:
    """Return one stable ID-ordered page; linked CRM identity is required."""
    if not 1 <= limit <= 100:
        raise ValueError("Page size must be between 1 and 100")
    if activity_filter not in ACTIVITY_FILTERS:
        raise ValueError("Unknown customer activity filter")
    if only_open_cases:
        activity_filter = "open_cases"
    root = Path(c360_root)
    gold = root / "golden_customers.parquet"
    crosswalk = root / "identity_crosswalk.parquet"
    if not gold.is_file() or not crosswalk.is_file():
        raise FileNotFoundError("Published C360 files are missing; run the C360 build")
    cache = root / CACHE.name
    if not cache.is_file():
        raise FileNotFoundError("Customer activity cache is missing; run python -m app.prepare_customer_data")

    activity_conditions = {
        "all": "",
        "open_cases": " AND g.open_case_count > 0",
        "any_promise": " AND coalesce(a.promise_count, 0) > 0",
        "broken_promise": " AND coalesce(a.broken_promise_count, 0) > 0",
        "open_promise": " AND coalesce(a.open_promise_count, 0) > 0",
        "open_cases_and_promises": " AND g.open_case_count > 0 "
                                   "AND coalesce(a.promise_count, 0) > 0",
    }

    query_filter = """
        FROM read_parquet({gold}) g
        LEFT JOIN customer_cache.customer_activity a
          ON a.golden_customer_id = g.golden_customer_id
        WHERE EXISTS (
            SELECT 1 FROM read_parquet({crosswalk}) x
            WHERE x.golden_customer_id = g.golden_customer_id
              AND x.source_system = 'crm' AND x.link_status = 'linked'
        )
          AND contains(lower(g.golden_customer_id), ?)
          {activity_condition}
    """.format(gold=_path(gold), crosswalk=_path(crosswalk),
               activity_condition=activity_conditions[activity_filter])
    terms = [search.strip().casefold()]
    con = duckdb.connect(":memory:")
    try:
        con.execute("SET memory_limit='1GB'")
        con.execute(f"ATTACH {_path(cache)} AS customer_cache (READ_ONLY)")
        total = con.execute("SELECT count(*) " + query_filter, terms).fetchone()[0]
        cursor_filter = " AND g.golden_customer_id > ?" if after_id else ""
        cursor_terms = terms + ([after_id] if after_id else [])
        cursor = con.execute(
            "SELECT g.golden_customer_id, g.open_case_count, g.max_current_dpd, "
            "g.total_overdue_cad, g.dq_status, "
            "coalesce(a.promise_count, 0) AS promise_count, "
            "coalesce(a.broken_promise_count, 0) AS broken_promise_count, "
            "coalesce(a.open_promise_count, 0) AS open_promise_count "
            + query_filter + cursor_filter +
            " ORDER BY g.golden_customer_id LIMIT ?",
            cursor_terms + [limit + 1],
        )
        names = [column[0] for column in cursor.description]
        fetched = [dict(zip(names, row)) for row in cursor.fetchall()]
        return {"total": total, "rows": fetched[:limit], "has_next": len(fetched) > limit}
    finally:
        con.close()
