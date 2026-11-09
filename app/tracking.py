"""Send log and the 1x1 open-tracking pixel."""

from __future__ import annotations

import base64

from flask import Blueprint, current_app, render_template, url_for

from .campaigns import get_owned_campaign
from .db import get_db
from .security import login_required

bp = Blueprint("tracking", __name__)

# A 1x1 transparent GIF, inlined so the pixel needs no static file or network.
PIXEL_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

SEND_LOG_SQL = """
SELECT cs.id, cs.email, cs.opened_at, cs.open_count, cs.unsubscribed_at,
       cs.open_token, cs.unsubscribe_token, s.name
FROM campaign_sends cs
LEFT JOIN subscribers s ON s.id = cs.subscriber_id
WHERE cs.campaign_id = ?
ORDER BY cs.id
"""


@bp.get("/campaigns/<int:campaign_id>/log")
@login_required
def log(campaign_id: int):
    campaign = get_owned_campaign(campaign_id)
    recipients = []
    if campaign["sent_at"] is not None:
        for row in get_db().execute(SEND_LOG_SQL, (campaign_id,)).fetchall():
            item = dict(row)
            item["pixel_url"] = url_for(
                "tracking.pixel", token=row["open_token"], _external=True
            )
            item["unsubscribe_url"] = url_for(
                "public.unsubscribe", token=row["unsubscribe_token"], _external=True
            )
            recipients.append(item)

    totals = {
        "sent": len(recipients),
        "opened": sum(1 for r in recipients if r["opened_at"]),
        "unsubscribed": sum(1 for r in recipients if r["unsubscribed_at"]),
    }
    return render_template(
        "campaigns/log.html", campaign=campaign, recipients=recipients, totals=totals
    )


@bp.get("/t/open/<token>.gif")
def pixel(token: str):
    """Record the first open only, then return the tracking image."""
    db = get_db()
    row = db.execute(
        "SELECT id, opened_at FROM campaign_sends WHERE open_token = ?", (token,)
    ).fetchone()
    if row is not None and row["opened_at"] is None:
        db.execute(
            "UPDATE campaign_sends SET opened_at = datetime('now'), "
            "open_count = open_count + 1 WHERE id = ? AND opened_at IS NULL",
            (row["id"],),
        )

    response = current_app.response_class(PIXEL_GIF, mimetype="image/gif")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response
