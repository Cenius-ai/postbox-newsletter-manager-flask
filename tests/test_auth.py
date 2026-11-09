"""Accounts, the demo login, route protection and CSRF."""

from __future__ import annotations

import pytest

from tests.conftest import csrf_from, post, sign_in


def test_root_redirects_anonymous_visitor_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_page_prints_the_demo_credentials(client):
    body = client.get("/login").get_data(as_text=True)
    assert "Demo: cenius@cenius.ai / cenius" in body
    assert 'data-demo-fill' in body


def test_demo_login_lands_on_the_dashboard(demo_client):
    assert demo_client.get("/").status_code == 302
    dashboard = demo_client.get("/dashboard")
    assert dashboard.status_code == 200
    body = dashboard.get_data(as_text=True)
    assert "Confirmed" in body
    assert "Log out" in body


def test_wrong_password_gives_one_generic_message(client):
    response = sign_in(client, password="***REDACTED-SECRET***")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Email or password is incorrect." in body
    assert "does not exist" not in body
    # Still signed out.
    assert client.get("/dashboard").status_code == 302


def test_username_also_signs_in(client):
    response = sign_in(client, email="cenius")
    assert response.status_code == 303


def test_logout_ends_the_session(demo_client):
    token = csrf_from(demo_client.get("/dashboard"))
    response = demo_client.post("/logout", data={"csrf_token": token})
    assert response.status_code == 303
    assert demo_client.get("/dashboard").status_code == 302


def test_registration_creates_an_account_and_rejects_duplicates(client):
    token = csrf_from(client.get("/register"))
    payload = {
        "email": "new.reader@example.com",
        "password": "a-good-password",
        "display_name": "New Reader",
        "csrf_token": token,
    }
    created = client.post("/register", data=payload)
    assert created.status_code == 303
    assert client.get("/dashboard").status_code == 200

    other = client.application.test_client()
    token = csrf_from(other.get("/register"))
    payload["csrf_token"] = token
    duplicate = other.post("/register", data=payload)
    assert duplicate.status_code == 200
    assert "already exists" in duplicate.get_data(as_text=True)


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard",
        "/lists",
        "/lists/1",
        "/lists/1/import",
        "/campaigns",
        "/campaigns/1/edit",
        "/campaigns/1/log",
    ],
)
def test_management_routes_are_protected(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_public_token_routes_are_not_walled(client):
    assert client.get("/confirm/not-a-real-token").status_code == 200
    assert client.get("/unsubscribe/not-a-real-token").status_code == 200
    pixel = client.get("/t/open/not-a-real-token.gif")
    assert pixel.status_code == 200
    assert pixel.headers["Content-Type"] == "image/gif"


def test_post_without_csrf_token_is_rejected_and_changes_nothing(demo_client, db):
    before = db.execute("SELECT COUNT(*) AS n FROM lists").fetchone()["n"]
    response = demo_client.post("/lists", data={"name": "Sneaky list"})
    assert response.status_code == 400
    after = db.execute("SELECT COUNT(*) AS n FROM lists").fetchone()["n"]
    assert after == before


def test_post_with_wrong_csrf_token_is_rejected(demo_client):
    response = demo_client.post(
        "/lists", data={"name": "Sneaky list", "csrf_token": "not-the-token"}
    )
    assert response.status_code == 400


def test_logged_in_visitor_is_sent_away_from_login(demo_client):
    response = demo_client.get("/login")
    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]


def test_security_headers_are_present(client):
    headers = client.get("/login").headers
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


def test_create_a_list_from_the_index(demo_client):
    token = csrf_from(demo_client.get("/lists"))
    response = demo_client.post(
        "/lists",
        data={
            "name": "Test Bench Notes",
            "description": "Weekly notes about the bench.",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Test Bench Notes" in body
    assert "0" in body  # zeroed counters on a brand new list


def test_post_helper_round_trip(demo_client, db):
    post(demo_client, "/lists", {"name": "Helper List", "description": ""})
    row = db.execute("SELECT * FROM lists WHERE name = 'Helper List'").fetchone()
    assert row is not None
