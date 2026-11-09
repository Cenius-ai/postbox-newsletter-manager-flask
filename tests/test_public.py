"""Public double opt-in confirmation, unsubscribe and the tracking pixel."""

from __future__ import annotations

from tests.conftest import csrf_from


def _pending(db, list_name="The Slow Web — Weekly"):
    list_id = db.execute("SELECT id FROM lists WHERE name = ?", (list_name,)).fetchone()["id"]
    return db.execute(
        "SELECT * FROM subscribers WHERE list_id = ? AND status = 'pending' LIMIT 1",
        (list_id,),
    ).fetchone()


def test_confirmation_page_is_public_and_names_the_subscriber(client, db):
    pending = _pending(db)
    response = client.get(f"/confirm/{pending['confirm_token']}")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert pending["email"] in body
    assert "The Slow Web — Weekly" in body
    assert "Confirm subscription" in body


def test_confirming_flips_the_subscriber_and_is_single_use(client, db):
    pending = _pending(db)
    token = pending["confirm_token"]

    page = client.get(f"/confirm/{token}")
    response = client.post(
        f"/confirm/{token}", data={"csrf_token": csrf_from(page)}, follow_redirects=True
    )
    assert response.status_code == 200
    assert "You are on the list" in response.get_data(as_text=True)

    row = db.execute("SELECT * FROM subscribers WHERE id = ?", (pending["id"],)).fetchone()
    assert row["status"] == "confirmed"
    assert row["confirmed_at"] is not None

    again = client.get(f"/confirm/{token}").get_data(as_text=True)
    assert "already confirmed" in again


def test_expired_token_explains_how_to_reissue(client, db):
    pending = _pending(db)
    db.execute(
        "UPDATE subscribers SET confirm_token_expires_at = '2020-01-01 00:00:00' WHERE id = ?",
        (pending["id"],),
    )
    body = client.get(f"/confirm/{pending['confirm_token']}").get_data(as_text=True)
    assert "has expired" in body
    assert "Resend" in body


def test_unknown_token_shows_the_invalid_state(client):
    body = client.get("/confirm/definitely-not-a-token").get_data(as_text=True)
    assert "not valid" in body


def test_pixel_records_only_the_first_open(client, db):
    send = db.execute(
        "SELECT * FROM campaign_sends WHERE campaign_id = 1 AND opened_at IS NULL LIMIT 1"
    ).fetchone()

    first = client.get(f"/t/open/{send['open_token']}.gif")
    assert first.status_code == 200
    assert first.headers["Content-Type"] == "image/gif"
    assert first.data[:3] == b"GIF"

    opened = db.execute(
        "SELECT opened_at, open_count FROM campaign_sends WHERE id = ?", (send["id"],)
    ).fetchone()
    assert opened["opened_at"] is not None
    assert opened["open_count"] == 1

    client.get(f"/t/open/{send['open_token']}.gif")
    second = db.execute(
        "SELECT opened_at, open_count FROM campaign_sends WHERE id = ?", (send["id"],)
    ).fetchone()
    assert second["opened_at"] == opened["opened_at"]
    assert second["open_count"] == 1


def test_unsubscribe_page_and_post_update_both_rows(client, db):
    send = db.execute(
        "SELECT cs.* FROM campaign_sends cs "
        "WHERE cs.campaign_id = 1 AND cs.unsubscribed_at IS NULL LIMIT 1"
    ).fetchone()

    page = client.get(f"/unsubscribe/{send['unsubscribe_token']}")
    body = page.get_data(as_text=True)
    assert send["email"] in body
    assert "Confirm unsubscribe" in body

    response = client.post(
        f"/unsubscribe/{send['unsubscribe_token']}",
        data={"csrf_token": csrf_from(page)},
        follow_redirects=True,
    )
    assert "You are unsubscribed" in response.get_data(as_text=True)

    refreshed = db.execute("SELECT * FROM campaign_sends WHERE id = ?", (send["id"],)).fetchone()
    assert refreshed["unsubscribed_at"] is not None
    subscriber = db.execute(
        "SELECT * FROM subscribers WHERE id = ?", (send["subscriber_id"],)
    ).fetchone()
    assert subscriber["status"] == "unsubscribed"

    again = client.get(f"/unsubscribe/{send['unsubscribe_token']}").get_data(as_text=True)
    assert "already unsubscribed" in again


def test_unknown_unsubscribe_token_is_invalid(client):
    body = client.get("/unsubscribe/nope").get_data(as_text=True)
    assert "not valid" in body
