from app.auth import authenticate


def test_demo_sign_in_uses_configured_password_and_fixed_roles(monkeypatch):
    monkeypatch.setenv("COLLECTIONS_DEMO_PASSWORD", "test-secret")
    assert authenticate("manager", "test-secret")["role"] == "manager"
    assert authenticate("agent", "test-secret")["role"] == "agent"
    assert authenticate("agent", "wrong") is None
    assert authenticate("unknown", "test-secret") is None
