"""Local demo sign-in for the two presentation roles.

This is a session gate for a local synthetic-data demo, not bank authentication.
"""

from __future__ import annotations

import hmac
import os

from dotenv import load_dotenv


ACCOUNTS = {
    "manager": {"user_id": "manager", "name": "Collection Manager", "role": "manager"},
    "agent": {"user_id": "agent", "name": "Collections Specialist", "role": "agent"},
}


def configured_password() -> bool:
    load_dotenv()
    return bool(os.getenv("COLLECTIONS_DEMO_PASSWORD"))


def authenticate(user_id: str, password: str) -> dict | None:
    """Return a role identity for the local demo when credentials match."""
    load_dotenv()
    account = ACCOUNTS.get(user_id.strip().lower())
    if account is None:
        return None
    expected = os.getenv("COLLECTIONS_DEMO_PASSWORD") or "demo"
    if not hmac.compare_digest(password, expected):
        return None
    return account.copy()
