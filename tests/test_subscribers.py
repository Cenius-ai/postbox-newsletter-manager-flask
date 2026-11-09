"""Subscribers: add, duplicate handling, resend and delete."""

from __future__ import annotations

from tests.conftest import post


def _list_id(db, name="The Slow Web — Weekly"):
    return db.execute("SELECT id FROM lists WHERE name = ?", (name,)).fetchone()["id"]


def test_add_subscriber_creates_a_pending_row_with_a_confirmation_link(demo_client, db):
    list_id = _list_id(db)
    response = post(
        demo_client,
        f"/lists/{list_id}/subscribers",
        {"email": "ada.lovelace@example.com", "name": "Ada Lovelace"},
        token_page=f"/lists/{list_id}",
    )
    assert response.status_code == 303

    row = db.execute(
        "SELECT * FROM subscribers WHERE lower(email) = 'ada.lovelace@example.com'"
    ).fetchone()
    assert row["status"] == "pending"
    assert row["confirm_token"]
    assert row["confirm_token_expires_at"]

    body = demo_client.get(f"/lists/{list_id}").get_data(as_text=True)
    assert "ada.lovelace@example.com" in body
    assert f"/confirm/{row['confirm_token']}" in body
    assert "pending" in body


def test_duplicate_address_in_another_case_is_rejected(demo_client, db):
    list_id = _list_id(db)
    before = db.execute("SELECT COUNT(*) AS n FROM subscribers").fetchone()["n"]
    response = post(
        demo_client,
        f"/lists/{list_id}/subscribers",
        {"email": "MARTA.NOWAK@example.com", "name": "Marta again"},
        token_page=f"/lists/{list_id}",
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "already on this list" in body
    assert db.execute("SELECT COUNT(*) AS n FROM subscribers").fetchone()["n"] == before


def test_invalid_email_is_rejected(demo_client, db):
    list_id = _list_id(db)
    response = post(
        demo_client,
        f"/lists/{list_id}/subscribers",
        {"email": "not-an-email", "name": ""},
        token_page=f"/lists/{list_id}",
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "does not look like an email address" in body
    assert (
        db.execute(
            "SELECT COUNT(*) AS n FROM subscribers WHERE email = 'not-an-email'"
        ).fetchone()["n"]
        == 0
    )


def test_list_header_counts_cover_all_three_statuses(demo_client, db):
    list_id = _list_id(db)
    body = demo_client.get(f"/lists/{list_id}").get_data(as_text=True)
    assert "Confirmed" in body
    assert "Pending" in body
    assert "Unsubscribed" in body
    for status in ("confirmed", "pending", "unsubscribed"):
        assert f"badge--{status}" in body


def test_resend_rotates_the_token_and_invalidates_the_old_link(demo_client, db):
    list_id = _list_id(db)
    pending = db.execute(
        "SELECT * FROM subscribers WHERE list_id = ? AND status = 'pending' LIMIT 1",
        (list_id,),
    ).fetchone()
    old_token = pending["confirm_token"]

    post(
        demo_client,
        f"/subscribers/{pending['id']}/resend-confirmation",
        {},
        token_page=f"/lists/{list_id}",
    )

    refreshed = db.execute("SELECT * FROM subscribers WHERE id = ?", (pending["id"],)).fetchone()
    assert refreshed["confirm_token"] != old_token
    assert "not valid" in demo_client.get(f"/confirm/{old_token}").get_data(as_text=True)
    assert pending["email"] in demo_client.get(
        f"/confirm/{refreshed['confirm_token']}"
    ).get_data(as_text=True)


def test_delete_subscriber_reduces_the_counts(demo_client, db):
    list_id = _list_id(db)
    subscriber = db.execute(
        "SELECT * FROM subscribers WHERE list_id = ? AND status = 'confirmed' LIMIT 1",
        (list_id,),
    ).fetchone()
    before = db.execute(
        "SELECT COUNT(*) AS n FROM subscribers WHERE list_id = ?", (list_id,)
    ).fetchone()["n"]

    post(
        demo_client,
        f"/subscribers/{subscriber['id']}/delete",
        {},
        token_page=f"/lists/{list_id}",
    )

    after = db.execute(
        "SELECT COUNT(*) AS n FROM subscribers WHERE list_id = ?", (list_id,)
    ).fetchone()["n"]
    assert after == before - 1
    assert (
        db.execute("SELECT id FROM subscribers WHERE id = ?", (subscriber["id"],)).fetchone()
        is None
    )


def test_subscriber_from_another_account_returns_404(other_client, db):
    subscriber = db.execute("SELECT * FROM subscribers LIMIT 1").fetchone()
    response = post(
        other_client, f"/subscribers/{subscriber['id']}/delete", {}, token_page="/lists"
    )
    assert response.status_code == 404
    assert (
        db.execute("SELECT id FROM subscribers WHERE id = ?", (subscriber["id"],)).fetchone()
        is not None
    )
