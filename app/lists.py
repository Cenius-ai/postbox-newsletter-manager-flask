"""Subscriber lists: index, create, detail, rename and delete."""

from __future__ import annotations

import sqlite3

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from .db import get_db, transaction
from .security import login_required
from .validation import (
    MAX_DESCRIPTION_LENGTH,
    MAX_LIST_NAME_LENGTH,
    clean_single_line,
    clean_text,
)

bp = Blueprint("lists", __name__)

LIST_SUMMARY_SQL = """
SELECT l.id, l.name, l.description, l.created_at,
       COUNT(s.id) AS total,
       COALESCE(SUM(CASE WHEN s.status = 'confirmed' THEN 1 ELSE 0 END), 0) AS confirmed,
       COALESCE(SUM(CASE WHEN s.status = 'pending' THEN 1 ELSE 0 END), 0) AS pending,
       COALESCE(SUM(CASE WHEN s.status = 'unsubscribed' THEN 1 ELSE 0 END), 0) AS unsubscribed
FROM lists l
LEFT JOIN subscribers s ON s.list_id = l.id
WHERE l.owner_id = ?
GROUP BY l.id
ORDER BY l.created_at DESC, l.id DESC
"""

SUBSCRIBERS_SQL = """
SELECT * FROM subscribers
WHERE list_id = ?
ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'confirmed' THEN 1 ELSE 2 END,
         lower(email)
"""


def get_owned_list(list_id: int) -> sqlite3.Row:
    """Fetch a list owned by the signed-in user, or 404 (never reveal others)."""
    row = get_db().execute(
        "SELECT * FROM lists WHERE id = ? AND owner_id = ?", (list_id, g.user["id"])
    ).fetchone()
    if row is None:
        abort(404)
    return row


def list_summary(list_id: int) -> dict:
    row = get_db().execute(
        "SELECT COUNT(s.id) AS total, "
        "COALESCE(SUM(CASE WHEN s.status = 'confirmed' THEN 1 ELSE 0 END), 0) AS confirmed, "
        "COALESCE(SUM(CASE WHEN s.status = 'pending' THEN 1 ELSE 0 END), 0) AS pending, "
        "COALESCE(SUM(CASE WHEN s.status = 'unsubscribed' THEN 1 ELSE 0 END), 0) AS unsubscribed "
        "FROM subscribers s WHERE s.list_id = ?",
        (list_id,),
    ).fetchone()
    return dict(row)


def subscribers_with_links(list_id: int) -> list[dict]:
    """Rows plus the copyable double opt-in link for pending subscribers."""
    subscribers = []
    for row in get_db().execute(SUBSCRIBERS_SQL, (list_id,)).fetchall():
        item = dict(row)
        item["confirm_url"] = (
            url_for("public.confirm", token=row["confirm_token"], _external=True)
            if row["confirm_token"] and row["status"] == "pending"
            else None
        )
        subscribers.append(item)
    return subscribers


def build_detail_context(
    list_id: int,
    *,
    subscriber_values: dict | None = None,
    errors: dict | None = None,
    edit_values: dict | None = None,
    edit_errors: dict | None = None,
) -> dict:
    list_row = get_owned_list(list_id)
    return {
        "list_row": list_row,
        "counts": list_summary(list_id),
        "subscribers": subscribers_with_links(list_id),
        "subscriber_values": subscriber_values or {"email": "", "name": ""},
        "errors": errors or {},
        "edit_values": edit_values or {"name": list_row["name"], "description": list_row["description"] or ""},
        "edit_errors": edit_errors or {},
    }


def validate_list_form(form) -> tuple[dict, dict]:
    name = clean_single_line(form.get("name"))
    description = clean_text(form.get("description"))
    errors: dict[str, str] = {}

    if not name:
        errors["name"] = "Give the list a name readers will recognise."
    elif len(name) > MAX_LIST_NAME_LENGTH:
        errors["name"] = f"Keep the name under {MAX_LIST_NAME_LENGTH} characters."
    if len(description) > MAX_DESCRIPTION_LENGTH:
        errors["description"] = (
            f"Keep the description under {MAX_DESCRIPTION_LENGTH} characters."
        )

    return {"name": name, "description": description}, errors


@bp.get("/lists")
@login_required
def index():
    rows = get_db().execute(LIST_SUMMARY_SQL, (g.user["id"],)).fetchall()
    return render_template(
        "lists/index.html",
        lists=rows,
        values={"name": "", "description": ""},
        errors={},
    )


@bp.post("/lists")
@login_required
def create():
    values, errors = validate_list_form(request.form)

    if not errors:
        cursor = get_db().execute(
            "INSERT INTO lists (owner_id, name, description) VALUES (?, ?, ?)",
            (g.user["id"], values["name"], values["description"] or None),
        )
        flash(f"List “{values['name']}” created.", "success")
        return redirect(url_for("lists.detail", list_id=int(cursor.lastrowid)), code=303)

    rows = get_db().execute(LIST_SUMMARY_SQL, (g.user["id"],)).fetchall()
    return render_template("lists/index.html", lists=rows, values=values, errors=errors)


@bp.get("/lists/<int:list_id>")
@login_required
def detail(list_id: int):
    return render_template("lists/detail.html", **build_detail_context(list_id))


@bp.post("/lists/<int:list_id>/edit")
@login_required
def edit(list_id: int):
    get_owned_list(list_id)
    values, errors = validate_list_form(request.form)

    if not errors:
        with transaction(get_db()) as conn:
            conn.execute(
                "UPDATE lists SET name = ?, description = ? WHERE id = ? AND owner_id = ?",
                (values["name"], values["description"] or None, list_id, g.user["id"]),
            )
        flash("List details updated.", "success")
        return redirect(url_for("lists.detail", list_id=list_id), code=303)

    return render_template(
        "lists/detail.html",
        **build_detail_context(list_id, edit_values=values, edit_errors=errors),
    )


@bp.post("/lists/<int:list_id>/delete")
@login_required
def delete(list_id: int):
    list_row = get_owned_list(list_id)
    typed_name = clean_single_line(request.form.get("confirm_name"))

    if typed_name != list_row["name"]:
        flash("Type the list name exactly to confirm deletion.", "error")
        return redirect(url_for("lists.detail", list_id=list_id), code=303)

    with transaction(get_db()) as conn:
        conn.execute(
            "DELETE FROM lists WHERE id = ? AND owner_id = ?", (list_id, g.user["id"])
        )
    flash(f"List “{list_row['name']}” and its subscribers were deleted.", "success")
    return redirect(url_for("lists.index"), code=303)
