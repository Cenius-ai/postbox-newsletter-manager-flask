"""Shared fixtures for the Postbox test suite.

Every test gets its own SQLite file (seeded with the demo data on boot, exactly
like a real run) so tests never depend on each other or on a previous run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app  # noqa: E402
from app.constants import DEMO_EMAIL, DEMO_PASSWORD  # noqa: E402
from app.db import get_db  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'postbox-test.db'}")
    monkeypatch.setenv("SECRET_KEY", "test-only-secret-key")
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    with app.app_context():
        yield get_db()


def csrf_from(response) -> str:
    body = response.get_data(as_text=True)
    match = CSRF_RE.search(body)
    assert match, "expected the page to carry a CSRF token"
    return match.group(1)


def sign_in(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    token = csrf_from(client.get("/login"))
    return client.post(
        "/login",
        data={"email": email, "password": password, "csrf_token": token},
    )


def post(client, path, data, *, token_page="/dashboard", **kwargs):
    """POST with a fresh session CSRF token taken from an authenticated page."""
    payload = dict(data)
    payload.setdefault("csrf_token", csrf_from(client.get(token_page)))
    return client.post(path, data=payload, **kwargs)


@pytest.fixture()
def demo_client(client):
    response = sign_in(client)
    assert response.status_code == 303, "the demo account must be able to sign in"
    return client


@pytest.fixture()
def other_client(app):
    """A second, independent account used for the ownership (IDOR) tests."""
    client = app.test_client()
    token = csrf_from(client.get("/register"))
    response = client.post(
        "/register",
        data={
            "email": "second.reader@example.com",
            "password": "second-password",
            "display_name": "Second Reader",
            "csrf_token": token,
        },
    )
    assert response.status_code == 303
    return client
