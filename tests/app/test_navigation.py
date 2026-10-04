"""The Ask page remains reachable without using the sidebar."""

import os
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_ask_is_available_in_top_navigation() -> None:
    app_path = Path(__file__).resolve().parents[2] / "app" / "main.py"
    app = AppTest.from_file(str(app_path), default_timeout=120).run()
    app.text_input(key="login_user").set_value("manager")
    app.text_input(key="login_password").set_value(
        os.environ.get("COLLECTIONS_DEMO_PASSWORD") or "demo"
    )
    app.button(key="login_submit").click().run()

    assert not app.exception
    app.button(key="top_nav_Ask Collections").click().run()

    assert not app.exception
    assert app.session_state.page == "Ask Collections"
