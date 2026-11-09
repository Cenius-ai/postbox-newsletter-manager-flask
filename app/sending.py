"""Single-shot campaign send.

The campaign is claimed with a conditional UPDATE inside one transaction, so
only one send can ever win regardless of how many recipients exist; the
recipient rows are inserted in that same transaction.
"""

from __future__ import annotations

import secrets

from flask import Blueprint, flash, redirect, url_for

from .campaigns import get_owned_campaign
from .db import get_db, transaction
from .security import login_required

bp = Blueprint("sending", __name__)

ALREADY_SENT = "This campaign was already sent. Nothing was sent twice."
NO_RECIPIENTS = (
    "There are no confirmed recipients on this list yet, so nothing was sent. "
    "The campaign is still a draft — invite subscribers and let them confirm first."
)


class AlreadySent(Exception):
    """Another request claimed the campaign first."""


class NoRecipients(Exception):
    """The list has no confirmed subscribers to receive this send."""


def deliver(campaign_id: int, list_id: int) -> int:
    """Claim the campaign and snapshot its confirmed recipients atomically."""
    conn = get_db()
    with transaction(conn):
        claimed = conn.execute(
            "UPDATE campaigns SET sent_at = datetime('now'), updated_at = datetime('now') "
            "WHERE id = ? AND sent_at IS NULL",
            (campaign_id,),
        )
        if claimed.rowcount != 1:
            raise AlreadySent

        recipients = conn.execute(
            "SELECT id, email FROM subscribers "
            "WHERE list_id = ? AND status = 'confirmed' ORDER BY lower(email)",
            (list_id,),
        ).fetchall()
        if not recipients:
            # Raising rolls the claim back, so the campaign stays a draft.
            raise NoRecipients

        for recipient in recipients:
            conn.execute(
                "INSERT OR IGNORE INTO campaign_sends (campaign_id, subscriber_id, email, "
                "open_token, unsubscribe_token) VALUES (?, ?, ?, ?, ?)",
                (
                    campaign_id,
                    recipient["id"],
                    recipient["email"],
                    secrets.token_urlsafe(32),
                    secrets.token_urlsafe(32),
                ),
            )
    return len(recipients)


@bp.post("/campaigns/<int:campaign_id>/send")
@login_required
def send(campaign_id: int):
    campaign = get_owned_campaign(campaign_id)

    if campaign["sent_at"] is not None:
        flash(ALREADY_SENT, "error")
        return redirect(url_for("campaigns.edit", campaign_id=campaign_id), code=303)

    confirmed = get_db().execute(
        "SELECT COUNT(*) AS n FROM subscribers WHERE list_id = ? AND status = 'confirmed'",
        (campaign["list_id"],),
    ).fetchone()["n"]
    if confirmed == 0:
        flash(NO_RECIPIENTS, "error")
        return redirect(url_for("campaigns.edit", campaign_id=campaign_id), code=303)

    try:
        sent_count = deliver(campaign_id, campaign["list_id"])
    except AlreadySent:
        flash(ALREADY_SENT, "error")
        return redirect(url_for("campaigns.edit", campaign_id=campaign_id), code=303)
    except NoRecipients:
        flash(NO_RECIPIENTS, "error")
        return redirect(url_for("campaigns.edit", campaign_id=campaign_id), code=303)

    flash(
        f"Campaign sent to {sent_count} confirmed "
        f"{'recipient' if sent_count == 1 else 'recipients'}. "
        "The send log tracks opens and unsubscribes.",
        "success",
    )
    return redirect(url_for("tracking.log", campaign_id=campaign_id), code=303)
