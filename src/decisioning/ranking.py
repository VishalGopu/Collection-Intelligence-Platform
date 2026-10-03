"""Explicit MVP assumptions, deliberately separate from safeguard data."""

from src.features.contacts import CHANNELS, RANKING_FIELDS, check_feature_columns


WEIGHTS = {"rpc_rate": 0.8, "relative_contact_cost": -0.2,
           "payment_plan_bonus_after_two_broken_promises": 0.05,
           "wait_score": 0.02}


def rank_actions(evidence: dict, broken: int, checks: dict) -> list[dict]:
    check_feature_columns(RANKING_FIELDS)
    observed_costs = [r["mean_contact_cost_cad"] for r in evidence.values()
                      if r["mean_contact_cost_cad"] is not None]
    cost_scale = max(observed_costs, default=1.0) or 1.0
    rows = []
    for channel in CHANNELS:
        if not checks[channel]["allowed"]:
            continue
        stats = evidence[channel]
        if stats["rpc_rate"] is None or stats["mean_contact_cost_cad"] is None:
            continue  # No evidence: do not invent a channel probability or cost.
        score = (WEIGHTS["rpc_rate"] * stats["smoothed_rpc_rate"]
                 + WEIGHTS["relative_contact_cost"] * stats["mean_contact_cost_cad"] / cost_scale)
        rows.append({"action": channel, "score": round(score, 6),
                     "channel": channel, "evidence": stats})
    call = next((row for row in rows if row["action"] == "call"), None)
    if call and broken >= 2 and checks["payment_plan_discussion"]["allowed"]:
        rows.append({**call, "action": "payment_plan_discussion",
                     "score": round(call["score"] + 0.05, 6)})
    if checks["wait"]["allowed"]:
        rows.append({"action": "wait", "score": WEIGHTS["wait_score"], "channel": None})
    return sorted(rows, key=lambda r: (-r["score"], r["action"]))


def explain(choice: dict, broken: int) -> str:
    if choice["action"] == "specialist_review":
        return "A support safeguard requires specialist review; normal collection actions are suppressed."
    if choice["action"] == "wait":
        return "Wait: no permitted channel with sufficient historical evidence exceeds the assumed contact threshold."
    stats = choice["evidence"]
    text = (f"{choice['channel'].upper()} had {stats['right_party_contacts']} right-party contacts "
            f"in {stats['attempts']} outbound attempts in the {stats['time_band']} band over the prior "
            f"90 days ({stats['rpc_rate']:.1%}), at an average cost of CAD "
            f"{stats['mean_contact_cost_cad']:.2f}; the assumed rate/cost weights favour this option.")
    if choice["action"] == "payment_plan_discussion":
        text += f" {broken} previously observed broken promises add the assumed payment-plan discussion bonus."
    return text
