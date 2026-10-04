"""Read-only, bounded browser over the published linked golden customers."""

from __future__ import annotations

from pathlib import Path

import duckdb

from app.customer import C360, _path


PAGE_SIZE = 25


def browse_customers(
    search: str = "", *, after_id: str | None = None,
    only_open_cases: bool = False, limit: int = PAGE_SIZE,
    c360_root: Path = C360,
) -> dict:
    """Return one stable ID-ordered page; linked CRM identity is required."""
    if not 1 <= limit <= 100:
        raise ValueError("Page size must be between 1 and 100")
    root = Path(c360_root)
    gold = root / "golden_customers.parquet"
    crosswalk = root / "identity_crosswalk.parquet"
    if not gold.is_file() or not crosswalk.is_file():
        raise FileNotFoundError("Published C360 files are missing; run the C360 build")

    query_filter = """
        FROM read_parquet({gold}) g
        WHERE EXISTS (
            SELECT 1 FROM read_parquet({crosswalk}) x
            WHERE x.golden_customer_id = g.golden_customer_id
              AND x.source_system = 'crm' AND x.link_status = 'linked'
        )
          AND contains(lower(g.golden_customer_id), ?)
          AND (? = false OR g.open_case_count > 0)
    """.format(gold=_path(gold), crosswalk=_path(crosswalk))
    terms = [search.strip().casefold(), only_open_cases]
    con = duckdb.connect(":memory:")
    try:
        con.execute("SET memory_limit='1GB'")
        total = con.execute("SELECT count(*) " + query_filter, terms).fetchone()[0]
        cursor_filter = " AND g.golden_customer_id > ?" if after_id else ""
        cursor_terms = terms + ([after_id] if after_id else [])
        cursor = con.execute(
            "SELECT g.golden_customer_id, g.open_case_count, g.max_current_dpd, "
            "g.total_overdue_cad, g.dq_status " + query_filter + cursor_filter +
            " ORDER BY g.golden_customer_id LIMIT ?",
            cursor_terms + [limit + 1],
        )
        names = [column[0] for column in cursor.description]
        fetched = [dict(zip(names, row)) for row in cursor.fetchall()]
        return {"total": total, "rows": fetched[:limit], "has_next": len(fetched) > limit}
    finally:
        con.close()
