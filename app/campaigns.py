"""Campaigns: index, Markdown composer with live preview, draft edit and delete."""

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
from .markdown_render import render_markdown
from .security import login_required
from .validation import (
    MAX_FROM_NAME_LENGTH,
    MAX_SUBJECT_LENGTH,
    clean_single_line,
    clean_text,
)

bp = Blueprint("campaigns", __name__)

PLACEHOLDER_BODY = """## A subject line to think about

Write the letter here. **Markdown works**: headings, lists, *emphasis*, `code`
and [links](https://example.com).

- What happened this week
- One thing worth reading
- What comes next
"""

CAMPAIGN_INDEX_SQL = """
SELECT c.id, c.list_id, c.subject, c.from_name, c.body_markdown, c.sent_at, c.created_at,
       l.name AS list_name,
       COUNT(cs.id) AS recipients,
       COALESCE(SUM(CASE WHEN cs.opened_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS opened,
       COALESCE(SUM(CASE WHEN cs.unsubscribed_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS unsubscribed,
       (SELECT COUNT(*) FROM subscribers s2
         WHERE s2.list_id = c.list_id AND s2.status = 'confirmed') AS confirmed_on_list
FROM campaigns c
JOIN lists l ON l.id = c.list_id
LEFT JOIN campaign_sends cs ON cs.campaign_id = c.id
WHERE l.owner_id = ?
GROUP BY c.id
ORDER BY COALESCE(c.sent_at, c.created_at) DESC, c.id DESC
"""

LIST_OPTIONS_SQL = """
SELECT l.id, l.name,
       COALESCE(SUM(CASE WHEN s.status = 'confirmed' THEN 1 ELSE 0 END), 0) AS confirmed
FROM lists l
LEFT JOIN subscribers s ON s.list_id = l.id
WHERE l.owner_id = ?
GROUP BY l.id
ORDER BY l.name COLLATE NOCASE
"""


def get_owned_campaign(campaign_id: int) -> sqlite3.Row:
    row = get_db().execute(
        "SELECT c.*, l.name AS list_name FROM campaigns c "
        "JOIN lists l ON l.id = c.list_id "
        "WHERE c.id = ? AND l.owner_id = ?",
        (campaign_id, g.user["id"]),
    ).fetchone()
    if row is None:
        abort(404)
    return row


def _list_options() -> list[sqlite3.Row]:
    return get_db().execute(LIST_OPTIONS_SQL, (g.user["id"],)).fetchall()


def _default_values() -> dict:
    """Pre-fill the first list so a new campaign is always sendable in one step."""
    options = _list_options()
    return {
        "subject": "",
        "from_name": (g.user["display_name"] or "").strip(),
        "list_id": str(options[0]["id"]) if options else "",
        "body_markdown": PLACEHOLDER_BODY,
    }


def _confirmed_count(options: list[sqlite3.Row], list_id: str | int | None) -> int:
    try:
        wanted = int(list_id)
    except (TypeError, ValueError):
        return 0
    for option in options:
        if option["id"] == wanted:
            return option["confirmed"]
    return 0


def validate_campaign_form(form, options: list[sqlite3.Row]) -> tuple[dict, dict]:
    values = {
        "subject": clean_single_line(form.get("subject")),
        "from_name": clean_single_line(form.get("from_name")),
        "list_id": (form.get("list_id") or "").strip(),
        "body_markdown": clean_text(form.get("body_markdown")),
    }
    errors: dict[str, str] = {}

    if not values["subject"]:
        errors["subject"] = "Every campaign needs a subject line."
    elif len(values["subject"]) > MAX_SUBJECT_LENGTH:
        errors["subject"] = f"Keep the subject under {MAX_SUBJECT_LENGTH} characters."

    if not values["from_name"]:
        errors["from_name"] = "Add the name subscribers see in their inbox."
    elif len(values["from_name"]) > MAX_FROM_NAME_LENGTH:
        errors["from_name"] = f"Keep the from name under {MAX_FROM_NAME_LENGTH} characters."

    if not any(str(option["id"]) == values["list_id"] for option in options):
        errors["list_id"] = "Choose the list this campaign goes to."

    if not values["body_markdown"]:
        errors["body_markdown"] = "Write the body before saving the draft."

    return values, errors


def composer_context(
    *,
    campaign: sqlite3.Row | None,
    values: dict,
    errors: dict,
    is_sent: bool,
) -> dict:
    options = _list_options()
    return {
        "campaign": campaign,
        "values": values,
        "errors": errors,
        "is_sent": is_sent,
        "lists": options,
        "preview_html": render_markdown(values["body_markdown"]),
        "recipient_count": _confirmed_count(options, values["list_id"]),
    }


def _campaign_values(campaign: sqlite3.Row) -> dict:
    return {
        "subject": campaign["subject"],
        "from_name": campaign["from_name"],
        "list_id": str(campaign["list_id"]),
        "body_markdown": campaign["body_markdown"],
    }


@bp.get("/campaigns")
@login_required
def index():
    rows = get_db().execute(CAMPAIGN_INDEX_SQL, (g.user["id"],)).fetchall()
    drafts = [row for row in rows if row["sent_at"] is None]
    sent = [row for row in rows if row["sent_at"] is not None]
    return render_template("campaigns/index.html", drafts=drafts, sent=sent, total=len(rows))


@bp.route("/campaigns/new", methods=["GET", "POST"])
@login_required
def create():
    options = _list_options()
    values = _default_values()
    errors: dict[str, str] = {}

    if request.method == "POST":
        values, errors = validate_campaign_form(request.form, options)
        if not errors:
            cursor = get_db().execute(
                "INSERT INTO campaigns (list_id, subject, from_name, body_markdown) "
                "VALUES (?, ?, ?, ?)",
                (
                    int(values["list_id"]),
                    values["subject"],
                    values["from_name"],
                    values["body_markdown"],
                ),
            )
            campaign_id = int(cursor.lastrowid)
            flash("Draft saved. Send it when you are ready.", "success")
            return redirect(url_for("campaigns.edit", campaign_id=campaign_id), code=303)

    return render_template(
        "campaigns/composer.html",
        **composer_context(campaign=None, values=values, errors=errors, is_sent=False),
    )


@bp.route("/campaigns/<int:campaign_id>/edit", methods=["GET", "POST"])
@login_required
def edit(campaign_id: int):
    campaign = get_owned_campaign(campaign_id)

    if request.method == "POST":
        if campaign["sent_at"] is not None:
            abort(
                400,
                description=(
                    "This campaign has already been sent. Sent campaigns are read-only, "
                    "so nothing was changed."
                ),
            )
        options = _list_options()
        values, errors = validate_campaign_form(request.form, options)
        if not errors:
            with transaction(get_db()) as conn:
                conn.execute(
                    "UPDATE campaigns SET list_id = ?, subject = ?, from_name = ?, "
                    "body_markdown = ?, updated_at = datetime('now') "
                    "WHERE id = ? AND sent_at IS NULL",
                    (
                        int(values["list_id"]),
                        values["subject"],
                        values["from_name"],
                        values["body_markdown"],
                        campaign_id,
                    ),
                )
            flash("Draft updated.", "success")
            return redirect(url_for("campaigns.edit", campaign_id=campaign_id), code=303)
        return render_template(
            "campaigns/composer.html",
            **composer_context(campaign=campaign, values=values, errors=errors, is_sent=False),
        )

    return render_template(
        "campaigns/composer.html",
        **composer_context(
            campaign=campaign,
            values=_campaign_values(campaign),
            errors={},
            is_sent=campaign["sent_at"] is not None,
        ),
    )


@bp.post("/campaigns/<int:campaign_id>/delete")
@login_required
def delete(campaign_id: int):
    campaign = get_owned_campaign(campaign_id)
    if campaign["sent_at"] is not None:
        abort(
            400,
            description=(
                "Sent campaigns cannot be deleted: the send log is the record of what "
                "went out. Nothing was changed."
            ),
        )
    with transaction(get_db()) as conn:
        conn.execute("DELETE FROM campaigns WHERE id = ? AND sent_at IS NULL", (campaign_id,))
    flash("Draft deleted.", "success")
    return redirect(url_for("campaigns.index"), code=303)
