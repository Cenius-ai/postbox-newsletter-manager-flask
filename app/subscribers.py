"""Subscribers inside a list: add, delete and resend double opt-in tokens."""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .constants import CONFIRM_TOKEN_DAYS, STAMP_FORMAT
from .db import get_db, transaction
from .lists import build_detail_context, get_owned_list
from .security import login_required
from .validation import MAX_NAME_LENGTH, clean_single_line, is_valid_email

bp = Blueprint("subscribers", __name__)


def get_owned_subscriber(subscriber_id: int) -> sqlite3.Row:
    row = get_db().execute(
        "SELECT s.*, l.name AS list_name FROM subscribers s "
        "JOIN lists l ON l.id = s.list_id "
        "WHERE s.id = ? AND l.owner_id = ?",
        (subscriber_id, g.user["id"]),
    ).fetchone()
    if row is None:
        abort(404)
    return row


def new_confirmation_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(days=CONFIRM_TOKEN_DAYS)).strftime(STAMP_FORMAT)
    return token, expires


@bp.post("/lists/<int:list_id>/subscribers")
@login_required
def create(list_id: int):
    get_owned_list(list_id)  # ownership check before any write
    values = {
        "email": clean_single_line(request.form.get("email")),
        "name": clean_single_line(request.form.get("name")),
    }
    errors: dict[str, str] = {}

    if not values["email"]:
        errors["email"] = "Enter the email address you want to invite."
    elif not is_valid_email(values["email"]):
        errors["email"] = "That does not look like an email address."
    if len(values["name"]) > MAX_NAME_LENGTH:
        errors["name"] = f"Keep the name under {MAX_NAME_LENGTH} characters."

    if not errors:
        duplicate = get_db().execute(
            "SELECT id FROM subscribers WHERE list_id = ? AND lower(email) = lower(?)",
            (list_id, values["email"]),
        ).fetchone()
        if duplicate is not None:
            errors["email"] = "That address is already on this list."

    if not errors:
        token, expires = new_confirmation_token()
        try:
            get_db().execute(
                "INSERT INTO subscribers (list_id, email, name, status, confirm_token, "
                "confirm_token_expires_at) VALUES (?, ?, ?, 'pending', ?, ?)",
                (list_id, values["email"], values["name"] or None, token, expires),
            )
        except sqlite3.IntegrityError:
            errors["email"] = "That address is already on this list."
        else:
            flash(
                f"{values['email']} was added as pending. Copy the confirmation link "
                "to complete the double opt-in.",
                "success",
            )
            return redirect(url_for("lists.detail", list_id=list_id), code=303)

    return render_template(
        "lists/detail.html",
        **build_detail_context(list_id, subscriber_values=values, errors=errors),
    )


@bp.post("/subscribers/<int:subscriber_id>/delete")
@login_required
def delete(subscriber_id: int):
    subscriber = get_owned_subscriber(subscriber_id)
    with transaction(get_db()) as conn:
        conn.execute("DELETE FROM subscribers WHERE id = ?", (subscriber_id,))
    flash(f"{subscriber['email']} was removed from “{subscriber['list_name']}”.", "success")
    return redirect(url_for("lists.detail", list_id=subscriber["list_id"]), code=303)


@bp.post("/subscribers/<int:subscriber_id>/resend-confirmation")
@login_required
def resend_confirmation(subscriber_id: int):
    subscriber = get_owned_subscriber(subscriber_id)
    list_id = subscriber["list_id"]

    if subscriber["status"] == "confirmed":
        flash(f"{subscriber['email']} has already confirmed. No new link was created.", "info")
        return redirect(url_for("lists.detail", list_id=list_id), code=303)
    if subscriber["status"] == "unsubscribed":
        flash(
            f"{subscriber['email']} unsubscribed. Add the address again to re-invite it.",
            "error",
        )
        return redirect(url_for("lists.detail", list_id=list_id), code=303)

    token, expires = new_confirmation_token()
    with transaction(get_db()) as conn:
        conn.execute(
            "UPDATE subscribers SET confirm_token = ?, confirm_token_expires_at = ?, "
            "status = 'pending', updated_at = datetime('now') WHERE id = ?",
            (token, expires, subscriber_id),
        )
    flash(
        f"A fresh confirmation link was issued for {subscriber['email']}. "
        "The previous link no longer works.",
        "success",
    )
    return redirect(url_for("lists.detail", list_id=list_id), code=303)
