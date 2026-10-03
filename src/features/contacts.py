"""Point-in-time contact evidence; no demographic or deposit inputs."""

from __future__ import annotations

from datetime import datetime, timezone


PROTECTED_FIELDS = frozenset({
    "gender_code", "marital_status", "citizenship_status", "household_size",
    "dependants_count", "newcomer_program_flag", "newcomer_arrival_date",
    "accessibility_needs_flag", "accessibility_type", "vulnerability_type",
    "customer_accent_region", "ccb_deposit_flag", "deposit_accounts.ccb_deposit_flag",
    "gender", "citizenship", "household_status", "newcomer_status", "accent",
    "age", "age_band", "date_of_birth",
})
ROUTING_ONLY_FIELDS = frozenset({
    "vulnerability_flag", "vulnerable_customer_flag", "vulnerability_disclosed_flag",
    "hardship_flag", "hardship_mentioned_flag",
})
RANKING_FIELDS = ("rpc_rate", "mean_contact_cost_cad", "prior_broken_promises")
CHANNELS = ("call", "sms", "email", "push")


def check_feature_columns(columns) -> None:
    forbidden = set(columns) & (PROTECTED_FIELDS | ROUTING_ONLY_FIELDS)
    if forbidden:
        raise ValueError(f"Forbidden feature columns: {sorted(forbidden)}")


def utc_cutoff(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Prediction time must have a timezone")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def time_band(hour: int) -> str:
    if not 0 <= hour <= 23:
        raise ValueError("Invalid local contact hour")
    return "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"


def channel_evidence(con, as_of: datetime, band: str) -> dict[str, dict]:
    """Use preceding 90 days, with a strict UTC cutoff and observed RPC labels.

    Rates are observational and are not estimates of causal channel effects.
    Laplace smoothing is an explicit MVP assumption; absent evidence is null.
    """
    cutoff = utc_cutoff(as_of)
    rows = con.execute("""
        SELECT channel, count(*) AS attempts,
               count(*) FILTER (WHERE rpc_flag) AS right_party_contacts,
               avg(contact_cost_cad) AS mean_cost,
               max(contact_ts_utc) AS latest_source_ts
        FROM contact_evidence
        WHERE direction = 'outbound'
          AND contact_ts_utc < ? AND contact_ts_utc >= ? - INTERVAL '90 days'
          AND rpc_flag IS NOT NULL
          AND CASE WHEN contact_hour_local < 12 THEN 'morning'
                   WHEN contact_hour_local < 17 THEN 'afternoon'
                   ELSE 'evening' END = ?
          AND contact_hour_local BETWEEN 0 AND 23
        GROUP BY channel
    """, [cutoff, cutoff, band]).fetchall()
    result = {c: {"attempts": 0, "right_party_contacts": 0,
                  "rpc_rate": None, "smoothed_rpc_rate": None,
                  "mean_contact_cost_cad": None, "latest_source_ts": None,
                  "time_band": band} for c in CHANNELS}
    for channel, attempts, rpc, cost, latest in rows:
        if channel in result:
            result[channel].update(
                attempts=attempts, right_party_contacts=rpc, rpc_rate=rpc / attempts,
                smoothed_rpc_rate=(rpc + 1) / (attempts + 2),
                mean_contact_cost_cad=float(cost) if cost is not None else None,
                latest_source_ts=latest.isoformat(),
            )
    return result


def prior_broken_promises(con, crm_ids: list[str], as_of: datetime) -> int:
    """Only outcomes already observed before prediction; never today's status early."""
    cutoff = utc_cutoff(as_of)
    return con.execute("""
        SELECT count(*) FROM promise_evidence
        WHERE crm_customer_id IN (SELECT unnest(?))
          AND ptp_created_ts < ? AND status_ts < ?
          AND status_ts >= ? - INTERVAL '90 days'
          AND ptp_status = 'broken'
    """, [crm_ids, cutoff, cutoff, cutoff]).fetchone()[0]
