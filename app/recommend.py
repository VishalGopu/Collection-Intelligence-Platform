"""App boundary for proposals, human review, and recent audit records."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from functools import lru_cache
from threading import RLock

from app.customer import C360, DATASET, GOLDEN_ID, ROOT


AUDIT_PATH = ROOT / "local_artifacts/decisioning/audit.sqlite"
CACHE_PATH = ROOT / "local_artifacts/decisioning/source_cache.duckdb"


def connected() -> bool:
    """Whether the merged decisioning engine can be imported."""
    try:
        from src.decisioning import RecommendationEngine  # noqa: F401
    except ImportError:
        return False
    return True


_ENGINE_LOCK = RLock()


@lru_cache(maxsize=1)
def _engine():
    from src.decisioning import RecommendationEngine

    return RecommendationEngine(
        data_dir=DATASET, c360_dir=C360, cache_path=CACHE_PATH,
        audit_path=AUDIT_PATH,
    )


def recommend(golden_customer_id: str) -> dict:
    if not GOLDEN_ID.fullmatch(golden_customer_id):
        raise ValueError("Select a published golden customer first")
    with _ENGINE_LOCK:
        engine = _engine()
        result = engine.recommend(golden_customer_id)
        if result.get("identity_mode") != "linked_c360":
            raise RuntimeError("Recommendation requires a published linked C360 identity")
        return result


def review(
    decision_id: str, *, disposition: str, reviewer: str,
    reason: str, action: str | None = None,
) -> dict:
    if not reviewer.strip() or not reason.strip():
        raise ValueError("Reviewer and reason are required")
    with _ENGINE_LOCK:
        engine = _engine()
        if disposition == "approve":
            return engine.approve(decision_id, reviewer, reason)
        if disposition == "modify":
            if not action:
                raise ValueError("Select an alternative action")
            return engine.modify(decision_id, reviewer, action, reason)
        if disposition == "reject":
            return engine.reject(decision_id, reviewer, reason)
        raise ValueError("Unknown review action")


def worklist(limit: int = 20) -> list[dict]:
    """Return the shared engine's cached open-promise ranking for Streamlit."""
    with _ENGINE_LOCK:
        return _engine().worklist(limit)


def latest_audit_rows(golden_customer_id: str, limit: int = 10) -> list[dict]:
    """Read local audit records for one customer without exposing model inputs."""
    if not GOLDEN_ID.fullmatch(golden_customer_id):
        return []
    if not AUDIT_PATH.is_file():
        return []
    con = sqlite3.connect(f"file:{AUDIT_PATH.resolve().as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("""
            SELECT d.decision_id, d.created_at, d.payload_json,
                   r.reviewed_at, r.reviewer, r.disposition, r.final_action, r.reason
            FROM decisions d LEFT JOIN review_events r ON r.decision_id = d.decision_id
            WHERE d.customer_id = ? ORDER BY d.created_at DESC LIMIT ?
        """, (golden_customer_id, max(1, min(limit, 50)))).fetchall()
    finally:
        con.close()
    return [{
        "decision_id": decision_id, "created_at": created_at,
        "proposed_action": json.loads(payload).get("action"),
        "reviewed_at": reviewed_at, "reviewer": reviewer,
        "disposition": disposition or "pending_review",
        "final_action": final_action, "review_reason": reason,
    } for decision_id, created_at, payload, reviewed_at, reviewer,
         disposition, final_action, reason in rows]
