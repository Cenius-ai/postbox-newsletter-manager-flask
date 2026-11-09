"""CSV import: duplicate merging, per-row validation and the import entry point."""

from __future__ import annotations

import io

from tests.conftest import csrf_from, post

CSV = """email,name
new.person@example.com,New Person
MARTA.NOWAK@example.com,Marta Nowak
not-an-email,Bad Address
,Missing Email
"""


def _slow_web(db):
    return db.execute("SELECT id FROM lists WHERE name = 'The Slow Web — Weekly'").fetchone()["id"]


def test_list_page_links_to_the_importer(demo_client, db):
    list_id = _slow_web(db)
    assert "Import CSV" in demo_client.get(f"/lists/{list_id}").get_data(as_text=True)
    assert "Import CSV" in demo_client.get("/lists").get_data(as_text=True)

    import_page = demo_client.get(f"/lists/{list_id}/import")
    assert import_page.status_code == 200
    body = import_page.get_data(as_text=True)
    assert "email,name" in body
    assert 'name="csv_file"' in body
    assert 'name="csv_text"' in body


def test_pasted_csv_imports_updates_and_skips(demo_client, db):
    list_id = _slow_web(db)
    response = post(
        demo_client,
        f"/lists/{list_id}/import",
        {"csv_text": CSV},
        token_page=f"/lists/{list_id}/import",
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Import finished" in body
    assert "is not a valid email address" in body
    assert "No email address in this row." in body

    imported = db.execute(
        "SELECT * FROM subscribers WHERE lower(email) = 'new.person@example.com'"
    ).fetchone()
    assert imported["status"] == "pending"
    assert imported["confirm_token"]

    marta = db.execute(
        "SELECT * FROM subscribers WHERE lower(email) = 'marta.nowak@example.com'"
    ).fetchone()
    assert marta["status"] == "confirmed"

    # No duplicate row was created for the existing address.
    assert (
        db.execute(
            "SELECT COUNT(*) AS n FROM subscribers WHERE lower(email) = 'marta.nowak@example.com'"
        ).fetchone()["n"]
        == 1
    )


def test_merging_updates_the_name_without_resetting_status(demo_client, db):
    list_id = _slow_web(db)
    post(
        demo_client,
        f"/lists/{list_id}/import",
        {"csv_text": "email,name\nmarta.nowak@example.com,Marta Nowak-Lindqvist\n"},
        token_page=f"/lists/{list_id}/import",
    )
    marta = db.execute(
        "SELECT * FROM subscribers WHERE lower(email) = 'marta.nowak@example.com'"
    ).fetchone()
    assert marta["name"] == "Marta Nowak-Lindqvist"
    assert marta["status"] == "confirmed"


def test_missing_header_is_reported_above_the_form(demo_client, db):
    list_id = _slow_web(db)
    response = post(
        demo_client,
        f"/lists/{list_id}/import",
        {"csv_text": "someone@example.com\n"},
        token_page=f"/lists/{list_id}/import",
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "must be a header" in body


def test_empty_submission_is_reported(demo_client, db):
    list_id = _slow_web(db)
    response = post(
        demo_client,
        f"/lists/{list_id}/import",
        {"csv_text": "   "},
        token_page=f"/lists/{list_id}/import",
    )
    assert "Paste some CSV text" in response.get_data(as_text=True)


def test_file_upload_runs_the_same_import(demo_client, db):
    list_id = _slow_web(db)
    page = demo_client.get(f"/lists/{list_id}/import")
    response = demo_client.post(
        f"/lists/{list_id}/import",
        data={
            "csv_text": "",
            "csv_file": (
                io.BytesIO(b"email,name\nfrom.file@example.com,From File\n"),
                "audience.csv",
            ),
            "csrf_token": csrf_from(page),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert "Import finished" in response.get_data(as_text=True)
    row = db.execute(
        "SELECT * FROM subscribers WHERE lower(email) = 'from.file@example.com'"
    ).fetchone()
    assert row["status"] == "pending"


def test_row_cap_is_enforced(demo_client, db):
    list_id = _slow_web(db)
    rows = "\n".join(f"reader{index}@example.com,Reader {index}" for index in range(5001))
    response = post(
        demo_client,
        f"/lists/{list_id}/import",
        {"csv_text": "email,name\n" + rows + "\n"},
        token_page=f"/lists/{list_id}/import",
    )
    body = response.get_data(as_text=True)
    assert "at most" in body
    assert (
        db.execute(
            "SELECT COUNT(*) AS n FROM subscribers WHERE email LIKE 'reader%@example.com'"
        ).fetchone()["n"]
        == 0
    )
