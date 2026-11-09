"""Public, signed-out pages: double opt-in confirmation and unsubscribe."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, render_template, request

from .constants import STAMP_FORMAT
from .db import get_db, transaction

bp = Blueprint("public", __name__)

CONFIRM_SQL = """
SELECT s.*, l.name AS list_name
FROM subscribers s
JOIN lists l ON l.id = s.list_id
WHERE s.confirm_token = ?
"""

UNSUBSCRIBE_SQL = """
SELECT cs.*, s.id AS subscriber_id, s.status AS subscriber_status,
       l.name AS list_name
FROM campaign_sends cs
JOIN campaigns c ON c.id = cs.campaign_id
JOIN lists l ON l.id = c.list_id
JOIN subscribers s ON s.id = cs.subscriber_id
WHERE cs.unsubscribe_token = ?
"""


def _now() -> str:
    return datetime.utcnow().strftime(STAMP_FORMAT)


def _confirm_state(row) -> str:
    if row is None:
        return "invalid"
    if row["confirmed_at"] is not None or row["status"] == "confirmed":
        return "confirmed"
    if row["confirm_token_expires_at"] and row["confirm_token_expires_at"] < _now():
        return "expired"
    return "pending"


@bp.route("/confirm/<token>", methods=["GET", "POST"])
def confirm(token: str):
    db = get_db()
    row = db.execute(CONFIRM_SQL, (token,)).fetchone()
    state = _confirm_state(row)

    if request.method == "POST" and state == "pending":
        with transaction(db) as conn:
            conn.execute(
                "UPDATE subscribers SET status = 'confirmed', confirmed_at = ?, "
                "confirm_token_expires_at = NULL, updated_at = ? "
                "WHERE id = ? AND confirmed_at IS NULL",
                (_now(), _now(), row["id"]),
            )
        row = db.execute(CONFIRM_SQL, (token,)).fetchone()
        state = "success"

    return render_template("public/confirm.html", state=state, subscriber=row)


@bp.route("/unsubscribe/<token>", methods=["GET", "POST"])
def unsubscribe(token: str):
    db = get_db()
    row = db.execute(UNSUBSCRIBE_SQL, (token,)).fetchone()

    if row is None:
        state = "invalid"
    elif row["unsubscribed_at"] is not None:
        state = "already"
    else:
        state = "pending"

    if request.method == "POST" and state == "pending":
        with transaction(db) as conn:
            conn.execute(
                "UPDATE campaign_sends SET unsubscribed_at = ? "
                "WHERE unsubscribe_token = ? AND unsubscribed_at IS NULL",
                (_now(), token),
            )
            conn.execute(
                "UPDATE subscribers SET status = 'unsubscribed', unsubscribed_at = ?, "
                "updated_at = ? WHERE id = ?",
                (_now(), _now(), row["subscriber_id"]),
            )
        row = db.execute(UNSUBSCRIBE_SQL, (token,)).fetchone()
        state = "success"

    return render_template("public/unsubscribe.html", state=state, send=row)
