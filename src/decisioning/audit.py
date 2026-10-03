"""Append-only recommendation and review events in a local SQLite database."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


class AuditStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # The Streamlit adapter serializes access to its shared engine with a lock.
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                customer_id TEXT NOT NULL, payload_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS review_events (
                event_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
                reviewed_at TEXT NOT NULL, reviewer TEXT NOT NULL,
                disposition TEXT NOT NULL CHECK(disposition IN ('approve','modify','reject')),
                original_action TEXT NOT NULL, final_action TEXT,
                reason TEXT NOT NULL, validation_json TEXT NOT NULL,
                UNIQUE(decision_id));
            CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decisions
              BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END;
            CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions
              BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON review_events
              BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON review_events
              BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END;
        """)

    def save(self, decision: dict) -> None:
        with self.connection:
            self.connection.execute("INSERT INTO decisions VALUES (?, ?, ?, ?)", [
                decision["decision_id"], datetime.now(timezone.utc).isoformat(),
                decision["customer_id"], json.dumps(decision),
            ])

    def get(self, decision_id: str) -> dict:
        row = self.connection.execute("SELECT payload_json FROM decisions WHERE decision_id = ?",
                                      [decision_id]).fetchone()
        if row is None:
            raise KeyError(f"Unknown decision {decision_id}")
        return json.loads(row[0])

    def review(self, decision_id: str, reviewer: str, disposition: str, reason: str,
               final_action: str | None, checks: dict) -> dict:
        if not reviewer.strip() or not reason.strip():
            raise ValueError("Reviewer and reason are required")
        if disposition not in {"approve", "modify", "reject"}:
            raise ValueError("Unknown disposition")
        decision = self.get(decision_id)
        if disposition == "reject":
            final_action = None
        elif not checks.get(final_action, {}).get("allowed", False):
            raise ValueError("Review cannot override a policy block")
        event = {"event_id": str(uuid4()), "decision_id": decision_id,
                 "reviewed_at": datetime.now(timezone.utc).isoformat(),
                 "reviewer": reviewer, "disposition": disposition,
                 "original_action": decision["action"], "final_action": final_action,
                 "reason": reason, "validation": checks}
        with self.connection:
            self.connection.execute("INSERT INTO review_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                event["event_id"], decision_id, event["reviewed_at"], reviewer, disposition,
                event["original_action"], final_action, reason, json.dumps(checks),
            ])
        return event

    def close(self):
        self.connection.close()
