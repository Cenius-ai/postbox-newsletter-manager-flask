"""Aggregate dashboard totals and the zeroed empty state."""

from __future__ import annotations

import re

KPI_RE = re.compile(r'kpi__value">(\d+)<')


def test_dashboard_totals_match_the_seeded_data(demo_client):
    body = demo_client.get("/dashboard").get_data(as_text=True)
    values = KPI_RE.findall(body)
    assert values[:3] == ["2", "9", "2"]  # lists, confirmed subscribers, sent campaigns
    assert "Recent sends" in body
    assert "Issue 42 — The quiet web" in body
    assert "Latest confirmations" in body
    assert "Quick actions" in body


def test_dashboard_counts_follow_new_subscribers(demo_client, db):
    list_id = db.execute("SELECT id FROM lists WHERE name = 'The Slow Web — Weekly'").fetchone()["id"]
    token = demo_client.get("/dashboard").get_data(as_text=True)
    assert KPI_RE.findall(token)[1] == "9"

    db.execute(
        "UPDATE subscribers SET status = 'confirmed', confirmed_at = datetime('now') "
        "WHERE list_id = ? AND status = 'pending'",
        (list_id,),
    )
    body = demo_client.get("/dashboard").get_data(as_text=True)
    assert KPI_RE.findall(body)[1] == "11"


def test_new_account_sees_the_zeroed_empty_state(other_client):
    body = other_client.get("/dashboard").get_data(as_text=True)
    assert "Nothing to count yet" in body
    assert "Create a list" in body
    assert KPI_RE.findall(body)[:2] == ["0", "0"]
