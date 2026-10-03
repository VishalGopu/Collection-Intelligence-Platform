"""Deterministic safeguards applied before ranking, including channel transport."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CHANNEL_ACTIONS = ("call", "sms", "email", "push", "payment_plan_discussion")
ALL_ACTIONS = CHANNEL_ACTIONS + ("wait", "specialist_review")


@dataclass
class DecisionContext:
    customer_id: str
    crm_ids: list[str]
    case_ids: list[str]
    as_of: datetime
    time_zone: str | None
    linked: bool = True
    identity_needs_review: bool = False
    consent: dict[str, bool] = field(default_factory=dict)
    hardship: bool = False
    # These are safeguards only; they never enter ranking or feature vectors.
    specialist_safeguard: bool = False
    holds: list[str] = field(default_factory=list)
    cease_contact: bool = False
    representative: bool = False
    call_attempts_7d: int = 0
    payment_reminders_7d: int = 0
    contact_cap_7d: int = 3
    sunday_permitted: bool = False
    permitted_start: str = "07:00"
    permitted_end: str = "21:00"
    holiday: bool | None = None
    specialist_agent_id: str | None = None


def local_time(context: DecisionContext):
    try:
        return context.as_of.astimezone(ZoneInfo(context.time_zone)) if context.time_zone else None
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return None


def policy_checks(context: DecisionContext) -> dict[str, dict]:
    """Return allow/block reasons for every action; unknown consent fails closed.

    The release policy limits calls and payment-request automated reminders.
    We conservatively count every outbound digital reminder against the cap.
    Unknown holiday status blocks outbound actions until a reviewer supplies it.
    """
    local = local_time(context)
    common = []
    if not context.linked or context.identity_needs_review:
        common.append("identity_not_approved")
    if not context.case_ids:
        common.append("no_open_case")
    common.extend(context.holds)
    if context.cease_contact:
        common.append("cease_communication")
    if context.representative:
        common.append("representative_contact_required")
    support = context.hardship or context.specialist_safeguard
    results = {}
    for action in ALL_ACTIONS:
        reasons = []
        if action in CHANNEL_ACTIONS:
            reasons.extend(common)
            if support:
                reasons.append("specialist_route_required")
            channel = "call" if action == "payment_plan_discussion" else action
            if context.consent.get(channel) is not True:
                reasons.append("channel_consent_missing_or_conflicting")
            if local is None:
                reasons.append("customer_time_zone_unknown")
            else:
                # Apply the contact window to all proposed collection channels.
                try:
                    start = max(time(7), time.fromisoformat(context.permitted_start))
                    end = min(time(21), time.fromisoformat(context.permitted_end))
                    if local.weekday() == 6:
                        if not context.sunday_permitted:
                            reasons.append("sunday_contact_not_permitted")
                        start, end = max(start, time(13)), min(end, time(17))
                    if not start <= local.time().replace(tzinfo=None) < end:
                        reasons.append("outside_permitted_local_hours")
                except (ValueError, TypeError):
                    reasons.append("contact_window_unknown")
                if context.holiday is not False:
                    reasons.append("statutory_holiday_or_calendar_unknown")
            if (context.call_attempts_7d + context.payment_reminders_7d
                    >= min(3, context.contact_cap_7d)):
                reasons.append("rolling_7_day_contact_cap")
        elif action == "specialist_review":
            if not support:
                reasons.append("no_specialist_route_needed")
            if context.holds or not context.linked or context.identity_needs_review:
                reasons.append("hold_or_identity_review_takes_precedence")
        results[action] = {"allowed": not reasons, "reasons": sorted(set(reasons)),
                           "transport": "call" if action == "payment_plan_discussion" else None}
    return results


def filter_actions(context: DecisionContext, scored_actions: list[dict]) -> list[dict]:
    """Scores cannot override policy, including an arbitrarily high score."""
    checks = policy_checks(context)
    return [row for row in scored_actions if checks.get(row["action"], {}).get("allowed", False)]
