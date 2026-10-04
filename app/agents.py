"""Read-only staffing context from the synthetic release."""

from __future__ import annotations

import csv
from pathlib import Path

from app.customer import DATASET


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def staffing_snapshot(as_of_date: str, dataset_root: Path = DATASET) -> dict:
    data = Path(dataset_root) / "data"
    agents = _rows(data / "agents.csv")
    shifts = [row for row in _rows(data / "agent_shifts.csv")
              if row["shift_date"] == as_of_date]
    active = {row["agent_id"]: row for row in agents if row["status"] == "active"}
    scheduled = {row["agent_id"] for row in shifts
                 if row["agent_id"] in active and row["absence_flag"].lower() == "false"}
    absent = {row["agent_id"] for row in shifts
              if row["agent_id"] in active and row["absence_flag"].lower() == "true"}
    certified = {agent_id for agent_id in scheduled
                 if active[agent_id]["vulnerable_customer_certified"].lower() == "true"}
    return {
        "active_agents": len(active),
        "scheduled_agents": len(scheduled),
        "absent_agents": len(absent),
        "scheduled_certified_agents": len(certified),
    }


def specialist_candidate(agent_id: str, as_of_date: str,
                         dataset_root: Path = DATASET) -> dict | None:
    """Show existing candidate and shift facts; do not reserve or assign work."""
    data = Path(dataset_root) / "data"
    agent = next((row for row in _rows(data / "agents.csv")
                  if row["agent_id"] == agent_id), None)
    if agent is None:
        return None
    shifts = [row for row in _rows(data / "agent_shifts.csv")
              if row["agent_id"] == agent_id and row["shift_date"] == as_of_date]
    return {
        "agent_id": agent_id,
        "name": agent["agent_display_name"],
        "team": agent["team_id"],
        "active": agent["status"] == "active",
        "certified": agent["vulnerable_customer_certified"].lower() == "true",
        "case_load": int(agent["current_case_load"]),
        "max_cases": int(agent["max_concurrent_cases"]),
        "shifts": [{"start": row["start_local"], "end": row["end_local"],
                    "queue": row["queue_assignment"],
                    "absent": row["absence_flag"].lower() == "true"} for row in shifts],
    }
