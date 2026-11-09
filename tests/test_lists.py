"""Subscriber lists: create, rename, delete and per-owner scoping."""

from __future__ import annotations

from tests.conftest import csrf_from, post


def test_lists_index_shows_seeded_lists_with_counts(demo_client):
    body = demo_client.get("/lists").get_data(as_text=True)
    assert "The Slow Web — Weekly" in body
    assert "Postbox Changelog" in body
    assert "Confirmed" in body and "Pending" in body


def test_create_list_then_see_it_on_the_index(demo_client, db):
    post(demo_client, "/lists", {"name": "Bench Notes", "description": "Weekly bench notes."})
    body = demo_client.get("/lists").get_data(as_text=True)
    assert "Bench Notes" in body
    row = db.execute("SELECT * FROM lists WHERE name = 'Bench Notes'").fetchone()
    assert row["description"] == "Weekly bench notes."


def test_blank_name_is_rejected_inline(demo_client, db):
    before = db.execute("SELECT COUNT(*) AS n FROM lists").fetchone()["n"]
    response = post(demo_client, "/lists", {"name": "   ", "description": "no name"})
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Give the list a name readers will recognise." in body
    assert db.execute("SELECT COUNT(*) AS n FROM lists").fetchone()["n"] == before


def test_rename_a_list(demo_client, db):
    list_id = db.execute("SELECT id FROM lists WHERE name = 'Postbox Changelog'").fetchone()["id"]
    post(
        demo_client,
        f"/lists/{list_id}/edit",
        {"name": "Postbox Release Notes", "description": "Renamed."},
    )
    row = db.execute("SELECT * FROM lists WHERE id = ?", (list_id,)).fetchone()
    assert row["name"] == "Postbox Release Notes"
    assert row["description"] == "Renamed."


def test_delete_requires_the_typed_name(demo_client, db):
    list_id = db.execute("SELECT id FROM lists WHERE name = 'Postbox Changelog'").fetchone()["id"]

    post(
        demo_client,
        f"/lists/{list_id}/delete",
        {"confirm_name": "wrong name"},
        token_page=f"/lists/{list_id}",
    )
    assert db.execute("SELECT id FROM lists WHERE id = ?", (list_id,)).fetchone() is not None

    post(
        demo_client,
        f"/lists/{list_id}/delete",
        {"confirm_name": "Postbox Changelog"},
        token_page=f"/lists/{list_id}",
    )
    assert db.execute("SELECT id FROM lists WHERE id = ?", (list_id,)).fetchone() is None
    leftovers = db.execute(
        "SELECT COUNT(*) AS n FROM subscribers WHERE list_id = ?", (list_id,)
    ).fetchone()["n"]
    assert leftovers == 0


def test_another_account_cannot_open_the_list(demo_client, other_client, db):
    list_id = db.execute("SELECT id FROM lists WHERE name = 'The Slow Web — Weekly'").fetchone()["id"]
    response = other_client.get(f"/lists/{list_id}")
    assert response.status_code == 404
    assert "The Slow Web" not in response.get_data(as_text=True)


def test_another_account_cannot_delete_the_list(other_client, db):
    list_id = db.execute("SELECT id FROM lists WHERE name = 'The Slow Web — Weekly'").fetchone()["id"]
    token = csrf_from(other_client.get("/lists"))
    response = other_client.post(
        f"/lists/{list_id}/delete",
        data={"confirm_name": "The Slow Web — Weekly", "csrf_token": token},
    )
    assert response.status_code == 404
    assert db.execute("SELECT id FROM lists WHERE id = ?", (list_id,)).fetchone() is not None
