"""Aggregate dashboard: totals, engagement and recent activity."""

from __future__ import annotations

from flask import Blueprint, g, redirect, render_template, url_for

from .db import get_db
from .security import login_required

bp = Blueprint("dashboard", __name__)

RECENT_SENDS_SQL = """
SELECT c.id, c.subject, c.sent_at, l.name AS list_name,
       COUNT(cs.id) AS sent,
       COALESCE(SUM(CASE WHEN cs.opened_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS opened,
       COALESCE(SUM(CASE WHEN cs.unsubscribed_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS unsubscribed
FROM campaigns c
JOIN lists l ON l.id = c.list_id
LEFT JOIN campaign_sends cs ON cs.campaign_id = c.id
WHERE l.owner_id = ? AND c.sent_at IS NOT NULL
GROUP BY c.id
ORDER BY c.sent_at DESC
LIMIT 5
"""

LATEST_CONFIRMED_SQL = """
SELECT s.email, s.name, s.confirmed_at, l.name AS list_name, l.id AS list_id
FROM subscribers s
JOIN lists l ON l.id = s.list_id
WHERE l.owner_id = ? AND s.status = 'confirmed'
ORDER BY COALESCE(s.confirmed_at, s.created_at) DESC
LIMIT 6
"""


@bp.get("/")
def root():
    if g.get("user") is None:
        return redirect(url_for("auth.login"))
    return redirect(url_for("dashboard.index"))


@bp.get("/dashboard")
@login_required
def index():
    db = get_db()
    owner_id = g.user["id"]

    list_count = db.execute(
        "SELECT COUNT(*) AS n FROM lists WHERE owner_id = ?", (owner_id,)
    ).fetchone()["n"]

    subscriber_counts = {"confirmed": 0, "pending": 0, "unsubscribed": 0}
    for row in db.execute(
        "SELECT s.status, COUNT(*) AS n FROM subscribers s "
        "JOIN lists l ON l.id = s.list_id WHERE l.owner_id = ? GROUP BY s.status",
        (owner_id,),
    ).fetchall():
        subscriber_counts[row["status"]] = row["n"]
    subscriber_total = sum(subscriber_counts.values())

    campaign_counts = {"draft": 0, "sent": 0}
    for row in db.execute(
        "SELECT (c.sent_at IS NOT NULL) AS is_sent, COUNT(*) AS n FROM campaigns c "
        "JOIN lists l ON l.id = c.list_id WHERE l.owner_id = ? GROUP BY is_sent",
        (owner_id,),
    ).fetchall():
        campaign_counts["sent" if row["is_sent"] else "draft"] = row["n"]

    engagement = db.execute(
        "SELECT COUNT(cs.id) AS sent, "
        "COALESCE(SUM(CASE WHEN cs.opened_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS opened, "
        "COALESCE(SUM(CASE WHEN cs.unsubscribed_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS unsubscribed "
        "FROM campaign_sends cs "
        "JOIN campaigns c ON c.id = cs.campaign_id "
        "JOIN lists l ON l.id = c.list_id "
        "WHERE l.owner_id = ? AND c.sent_at IS NOT NULL",
        (owner_id,),
    ).fetchone()

    open_rate = (
        round(engagement["opened"] * 100 / engagement["sent"]) if engagement["sent"] else 0
    )
    unsubscribe_rate = (
        round(engagement["unsubscribed"] * 100 / engagement["sent"]) if engagement["sent"] else 0
    )

    return render_template(
        "dashboard.html",
        list_count=list_count,
        subscriber_counts=subscriber_counts,
        subscriber_total=subscriber_total,
        campaign_counts=campaign_counts,
        engagement=engagement,
        open_rate=open_rate,
        unsubscribe_rate=unsubscribe_rate,
        recent_sends=db.execute(RECENT_SENDS_SQL, (owner_id,)).fetchall(),
        latest_confirmed=db.execute(LATEST_CONFIRMED_SQL, (owner_id,)).fetchall(),
        is_empty=list_count == 0 and subscriber_total == 0,
    )
