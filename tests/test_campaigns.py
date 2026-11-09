"""Campaign composer, draft CRUD and the atomic send."""

from __future__ import annotations

from tests.conftest import csrf_from, post


def _make_list(demo_client, db, name="Send Bench"):
    post(demo_client, "/lists", {"name": name, "description": "Send tests."})
    return db.execute("SELECT id FROM lists WHERE name = ?", (name,)).fetchone()["id"]


def _add_subscriber(demo_client, db, list_id, email, status):
    post(
        demo_client,
        f"/lists/{list_id}/subscribers",
        {"email": email, "name": ""},
        token_page=f"/lists/{list_id}",
    )
    if status == "confirmed":
        db.execute(
            "UPDATE subscribers SET status = 'confirmed', confirmed_at = datetime('now') "
            "WHERE lower(email) = lower(?)",
            (email,),
        )
    else:
        db.execute(
            "UPDATE subscribers SET status = ? WHERE lower(email) = lower(?)",
            (status, email),
        )


def _new_campaign(demo_client, db, list_id, subject="Bench send"):
    response = post(
        demo_client,
        "/campaigns/new",
        {
            "subject": subject,
            "from_name": "Postbox",
            "list_id": str(list_id),
            "body_markdown": "## Hello\n\nA **bold** opening.\n\n- one\n- two",
        },
        token_page="/campaigns/new",
    )
    assert response.status_code == 303
    return db.execute("SELECT id FROM campaigns WHERE subject = ?", (subject,)).fetchone()["id"]


def test_composer_prefills_and_renders_the_preview(demo_client):
    body = demo_client.get("/campaigns/new").get_data(as_text=True)
    assert 'id="body_markdown"' in body
    assert "md-preview" in body
    assert "<strong>Markdown works</strong>" in body


def test_campaign_index_lists_drafts_and_sent(demo_client):
    body = demo_client.get("/campaigns").get_data(as_text=True)
    assert "Issue 43 — The tools we keep coming back to" in body
    assert "Issue 42 — The quiet web" in body
    assert "Send log" in body


def test_blank_subject_is_rejected(demo_client, db):
    list_id = db.execute("SELECT id FROM lists LIMIT 1").fetchone()["id"]
    before = db.execute("SELECT COUNT(*) AS n FROM campaigns").fetchone()["n"]
    response = post(
        demo_client,
        "/campaigns/new",
        {"subject": "", "from_name": "Postbox", "list_id": str(list_id), "body_markdown": "Body"},
        token_page="/campaigns/new",
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Every campaign needs a subject line." in body
    assert db.execute("SELECT COUNT(*) AS n FROM campaigns").fetchone()["n"] == before


def test_draft_can_be_edited_and_deleted(demo_client, db):
    list_id = _make_list(demo_client, db)
    campaign_id = _new_campaign(demo_client, db, list_id)

    post(
        demo_client,
        f"/campaigns/{campaign_id}/edit",
        {
            "subject": "Bench send, revised",
            "from_name": "Postbox",
            "list_id": str(list_id),
            "body_markdown": "Updated body.",
        },
        token_page=f"/campaigns/{campaign_id}/edit",
    )
    row = db.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    assert row["subject"] == "Bench send, revised"
    assert row["body_markdown"] == "Updated body."

    post(
        demo_client,
        f"/campaigns/{campaign_id}/delete",
        {},
        token_page=f"/campaigns/{campaign_id}/edit",
    )
    assert db.execute("SELECT id FROM campaigns WHERE id = ?", (campaign_id,)).fetchone() is None


def test_send_only_reaches_confirmed_subscribers(demo_client, db):
    list_id = _make_list(demo_client, db)
    _add_subscriber(demo_client, db, list_id, "one@example.com", "confirmed")
    _add_subscriber(demo_client, db, list_id, "two@example.com", "confirmed")
    _add_subscriber(demo_client, db, list_id, "three@example.com", "pending")
    campaign_id = _new_campaign(demo_client, db, list_id)

    response = post(
        demo_client,
        f"/campaigns/{campaign_id}/send",
        {},
        token_page=f"/campaigns/{campaign_id}/edit",
    )
    assert response.status_code == 303
    assert f"/campaigns/{campaign_id}/log" in response.headers["Location"]

    sends = db.execute(
        "SELECT * FROM campaign_sends WHERE campaign_id = ?", (campaign_id,)
    ).fetchall()
    assert len(sends) == 2
    assert {row["email"] for row in sends} == {"one@example.com", "two@example.com"}
    assert all(row["open_token"] and row["unsubscribe_token"] for row in sends)

    campaign = db.execute("SELECT sent_at FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    assert campaign["sent_at"] is not None


def test_a_second_send_is_refused(demo_client, db):
    list_id = _make_list(demo_client, db)
    _add_subscriber(demo_client, db, list_id, "solo@example.com", "confirmed")
    campaign_id = _new_campaign(demo_client, db, list_id, subject="Send once")

    token = csrf_from(demo_client.get(f"/campaigns/{campaign_id}/edit"))
    demo_client.post(f"/campaigns/{campaign_id}/send", data={"csrf_token": token})
    second = demo_client.post(
        f"/campaigns/{campaign_id}/send", data={"csrf_token": token}, follow_redirects=True
    )
    assert "already sent" in second.get_data(as_text=True)

    sends = db.execute(
        "SELECT COUNT(*) AS n FROM campaign_sends WHERE campaign_id = ?", (campaign_id,)
    ).fetchone()["n"]
    assert sends == 1


def test_sent_campaign_is_read_only(demo_client, db):
    list_id = _make_list(demo_client, db)
    _add_subscriber(demo_client, db, list_id, "readonly@example.com", "confirmed")
    campaign_id = _new_campaign(demo_client, db, list_id, subject="Read only send")
    token = csrf_from(demo_client.get(f"/campaigns/{campaign_id}/edit"))
    demo_client.post(f"/campaigns/{campaign_id}/send", data={"csrf_token": token})

    view = demo_client.get(f"/campaigns/{campaign_id}/edit")
    body = view.get_data(as_text=True)
    assert view.status_code == 200
    assert "has been sent" in body
    assert "readonly" in body
    assert "Send campaign" not in body

    edit = demo_client.post(
        f"/campaigns/{campaign_id}/edit",
        data={
            "subject": "Sneaky edit",
            "from_name": "Postbox",
            "list_id": str(list_id),
            "body_markdown": "nope",
            "csrf_token": token,
        },
    )
    assert edit.status_code == 400

    delete = demo_client.post(f"/campaigns/{campaign_id}/delete", data={"csrf_token": token})
    assert delete.status_code == 400

    campaign = db.execute(
        "SELECT subject, sent_at FROM campaigns WHERE id = ?", (campaign_id,)
    ).fetchone()
    assert campaign["subject"] == "Read only send"
    assert campaign["sent_at"] is not None


def test_send_without_confirmed_recipients_keeps_the_draft(demo_client, db):
    list_id = _make_list(demo_client, db, name="Empty Bench")
    campaign_id = _new_campaign(demo_client, db, list_id, subject="No one to send to")

    response = post(
        demo_client,
        f"/campaigns/{campaign_id}/send",
        {},
        token_page=f"/campaigns/{campaign_id}/edit",
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert "no confirmed recipients" in body.lower()

    campaign = db.execute("SELECT sent_at FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    assert campaign["sent_at"] is None
    assert (
        db.execute(
            "SELECT COUNT(*) AS n FROM campaign_sends WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()["n"]
        == 0
    )


def test_send_log_lists_recipients_and_totals(demo_client):
    body = demo_client.get("/campaigns/1/log").get_data(as_text=True)
    assert "badge--confirmed" in body
    assert "Open pixel" in body
    assert "Copy unsubscribe" in body
    assert "/t/open/" in body
    assert "/unsubscribe/" in body
    assert "Open rate" in body or "open rate" in body


def test_draft_log_explains_there_is_nothing_to_show(demo_client, db):
    draft = db.execute("SELECT id FROM campaigns WHERE sent_at IS NULL").fetchone()
    body = demo_client.get(f"/campaigns/{draft['id']}/log").get_data(as_text=True)
    assert "No send log for a draft" in body


def test_campaigns_of_another_account_are_not_found(other_client, db):
    campaign_id = db.execute("SELECT id FROM campaigns LIMIT 1").fetchone()["id"]
    assert other_client.get(f"/campaigns/{campaign_id}/edit").status_code == 404
    assert other_client.get(f"/campaigns/{campaign_id}/log").status_code == 404
