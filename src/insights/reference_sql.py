"""Hand-checked independent SQL for new-question regression checks."""

from __future__ import annotations

from collections import Counter


REFERENCE_SQL = {
    "NQ-001": "SELECT assigned_team, avg(current_dpd) FROM collections_cases WHERE case_status='open' GROUP BY assigned_team",
    "NQ-002": "SELECT assigned_team, count(*) FROM collections_cases WHERE case_status='open' GROUP BY assigned_team",
    "NQ-003": "SELECT primary_product, avg(current_dpd) FROM collections_cases WHERE case_status='open' GROUP BY primary_product",
    "NQ-005": "SELECT count(*) FILTER (WHERE ptp_status='kept')::DOUBLE / nullif(count(*) FILTER (WHERE ptp_status IN ('kept','partially_kept','broken')),0) FROM promises_to_pay WHERE ptp_due_date >= DATE '2026-07-01' AND ptp_due_date < DATE '2026-08-01'",
    "NQ-007": "SELECT contact_hour_local, count(*) FROM contact_history WHERE direction='outbound' AND coalesce(channel_v2,channel)='call' AND contact_ts_local >= TIMESTAMP '2026-09-01' AND contact_ts_local < TIMESTAMP '2026-10-01' GROUP BY contact_hour_local",
    "NQ-008": "SELECT assigned_team, count(*) FROM collections_cases WHERE case_status='open' GROUP BY assigned_team",
    "NQ-009": "SELECT queue, avg(current_dpd) FROM collections_cases WHERE case_status='open' GROUP BY queue",
    "NQ-011": "SELECT contact_hour_local, count(*) FILTER (WHERE rpc_flag)::DOUBLE / nullif(count(*),0) FROM contact_history WHERE direction='outbound' AND coalesce(channel_v2,channel)='call' AND contact_ts_local >= TIMESTAMP '2026-09-01' AND contact_ts_local < TIMESTAMP '2026-10-01' GROUP BY contact_hour_local",
    "NQ-012": "SELECT count(*) FROM collections_cases WHERE case_open_date >= DATE '2026-08-01' AND case_open_date < DATE '2026-09-01'",
    "NQ-013": "SELECT count(*) FROM collections_cases WHERE case_status='open' AND current_dpd > 5000",
}


def compare_rows(actual: list[tuple], expected: list[tuple]) -> bool:
    def normalize(rows: list[tuple]) -> Counter:
        normalized = []
        for row in rows:
            normalized.append(tuple(round(float(value), 6) if isinstance(value, float) else value for value in row))
        return Counter(normalized)

    return normalize(actual) == normalize(expected)
