"""Idempotent demo data.

The seed runs from ``python3 -m seed`` and again on every application boot (it
checks before it inserts), so a fresh clone always opens on a populated app and
so does a second run. Content is deliberately plausible: a real-looking weekly
essay list, a changelog list, subscribers in all three states and one sent
campaign that already has an open and an unsubscribe recorded.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from .constants import (
    CONFIRM_TOKEN_DAYS,
    DEMO_DISPLAY_NAME,
    DEMO_EMAIL,
    DEMO_PASSWORD,
    DEMO_USERNAME,
    STAMP_FORMAT,
)
from .db import transaction

# key -> (name, description)
LIST_SPECS = [
    (
        "slowweb",
        "The Slow Web — Weekly",
        "Friday essays on calmer software, slower internet and building small things "
        "that last. Sent to readers who prefer a quiet inbox.",
    ),
    (
        "changelog",
        "Postbox Changelog",
        "Release notes for the self-hosted Postbox server: new features, fixes and "
        "the occasional migration note.",
    ),
]

# (list key, email, name, status, days_ago_joined, days_ago_confirmed)
SUBSCRIBER_SPECS = [
    ("slowweb", "marta.nowak@example.com", "Marta Nowak", "confirmed", 46, 44),
    ("slowweb", "desmond.achebe@example.com", "Desmond Achebe", "confirmed", 39, 37),
    ("slowweb", "priya.raman@example.com", "Priya Raman", "confirmed", 31, 29),
    ("slowweb", "tobias.lindqvist@example.com", "Tobias Lindqvist", "confirmed", 24, 22),
    ("slowweb", "hana.yamada@example.com", "Hana Yamada", "confirmed", 15, 13),
    ("slowweb", "iker.etxeberria@example.com", "Iker Etxeberria", "confirmed", 6, 5),
    ("slowweb", "noor.haddad@example.com", "Noor Haddad", "pending", 2, None),
    ("slowweb", "felix.braun@example.com", "Felix Braun", "pending", 1, None),
    ("slowweb", "greta.osei@example.com", "Greta Osei", "unsubscribed", 27, 26),
    ("slowweb", "rodrigo.salas@example.com", "Rodrigo Salas", "unsubscribed", 9, 8),
    ("changelog", "amina.diallo@example.com", "Amina Diallo", "confirmed", 20, 19),
    ("changelog", "joonho.park@example.com", "Joon-ho Park", "confirmed", 17, 16),
    ("changelog", "clara.moreau@example.com", "Clara Moreau", "confirmed", 11, 10),
    ("changelog", "sam.okonkwo@example.com", "Sam Okonkwo", "pending", 3, None),
    ("changelog", "lena.vogel@example.com", "Lena Vogel", "unsubscribed", 15, 14),
]

SLOW_WEB_ISSUE_42 = """## The quiet web

Two weeks ago I deleted every app that sends me a notification I did not ask
for. The surprise was not how much I missed — it was how little.

- **Calmer defaults.** Software that is quiet unless something is wrong.
- **Fewer surfaces.** One page that does the whole job beats five that share it.
- **Slower rhythms.** A weekly letter is a promise, not a growth channel.

> Attention is the only budget that never refills mid-month.

If that sounds like your kind of internet, the [archive](https://example.com/archive)
now goes back to issue 1.

---

Next week: the tools I keep coming back to, and why `make` outlived them all.
"""

CHANGELOG_04 = """## Postbox 0.4

This release is mostly about importing the audience you already have.

- CSV import with **duplicate-address merging**, reachable from every list.
- A send log that records the first open only, so counts stay honest.
- Public unsubscribe pages that do not require an account.

Existing databases upgrade in place: the schema is safe to re-run. See the
[migration notes](https://example.com/postbox/upgrade) for the short version.
"""

ISSUE_43_DRAFT = """## The tools we keep coming back to

A short list, written on a train.

1. `make` — still the cheapest way to describe a build.
2. A plain text file of links, sorted by nothing.
3. The one notebook I have not lost yet.

I want to argue that boring tools are a feature, not an apology. Draft notes
below; the argument needs another pass before it goes out.
"""

CAMPAIGN_SPECS = [
    {
        "list": "slowweb",
        "subject": "Issue 42 — The quiet web",
        "from_name": "Slow Web Weekly",
        "body": SLOW_WEB_ISSUE_42,
        "days_ago_sent": 3,
        # email -> days ago the first open was recorded
        "opened": {"marta.nowak@example.com": 3, "priya.raman@example.com": 2},
        # recipient who unsubscribed from this send
        "unsubscribed": {"greta.osei@example.com": 2},
    },
    {
        "list": "changelog",
        "subject": "Postbox 0.4 — CSV import and send logs",
        "from_name": "Postbox",
        "body": CHANGELOG_04,
        "days_ago_sent": 12,
        "opened": {"amina.diallo@example.com": 11, "clara.moreau@example.com": 10},
        "unsubscribed": {},
    },
    {
        "list": "slowweb",
        "subject": "Issue 43 — The tools we keep coming back to",
        "from_name": "Slow Web Weekly",
        "body": ISSUE_43_DRAFT,
        "days_ago_sent": None,
        "opened": {},
        "unsubscribed": {},
    },
]


def stamp(days_ago: float) -> str:
    moment = datetime.utcnow() - timedelta(days=days_ago)
    return moment.strftime(STAMP_FORMAT)


def _ensure_user(conn: sqlite3.Connection) -> tuple[int, bool]:
    row = conn.execute("SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone()
    if row is not None:
        return row["id"], False
    cursor = conn.execute(
        "INSERT INTO users (email, username, display_name, password_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            DEMO_EMAIL,
            DEMO_USERNAME,
            DEMO_DISPLAY_NAME,
            generate_password_hash(DEMO_PASSWORD),
            stamp(60),
        ),
    )
    return int(cursor.lastrowid), True


def _ensure_list(
    conn: sqlite3.Connection, owner_id: int, name: str, description: str
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM lists WHERE owner_id = ? AND name = ?", (owner_id, name)
    ).fetchone()
    if row is not None:
        return row["id"], False
    cursor = conn.execute(
        "INSERT INTO lists (owner_id, name, description, created_at) VALUES (?, ?, ?, ?)",
        (owner_id, name, description, stamp(58)),
    )
    return int(cursor.lastrowid), True


def _ensure_subscriber(
    conn: sqlite3.Connection,
    list_id: int,
    email: str,
    name: str,
    status: str,
    days_ago_joined: int,
    days_ago_confirmed: int | None,
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM subscribers WHERE list_id = ? AND lower(email) = lower(?)",
        (list_id, email),
    ).fetchone()
    if row is not None:
        return row["id"], False

    confirmed_at = stamp(days_ago_confirmed) if days_ago_confirmed is not None else None
    unsubscribed_at = stamp(max(days_ago_joined - 1, 0)) if status == "unsubscribed" else None
    if status == "pending":
        confirm_token = secrets.token_urlsafe(32)
        expires_at = (datetime.utcnow() + timedelta(days=CONFIRM_TOKEN_DAYS)).strftime(
            STAMP_FORMAT
        )
    else:
        confirm_token = None
        expires_at = None

    updated_at = unsubscribed_at or confirmed_at or stamp(days_ago_joined)
    cursor = conn.execute(
        "INSERT INTO subscribers (list_id, email, name, status, confirm_token, "
        "confirm_token_expires_at, confirmed_at, unsubscribed_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            list_id,
            email,
            name,
            status,
            confirm_token,
            expires_at,
            confirmed_at,
            unsubscribed_at,
            stamp(days_ago_joined),
            updated_at,
        ),
    )
    return int(cursor.lastrowid), True


def _campaign_recipients(conn: sqlite3.Connection, list_id: int, spec: dict) -> list:
    """Confirmed subscribers at send time, plus anyone who unsubscribed from it."""
    recipients = list(
        conn.execute(
            "SELECT id, email FROM subscribers WHERE list_id = ? AND status = 'confirmed'",
            (list_id,),
        ).fetchall()
    )
    for email in spec["unsubscribed"]:
        row = conn.execute(
            "SELECT id, email FROM subscribers WHERE list_id = ? AND lower(email) = lower(?)",
            (list_id, email),
        ).fetchone()
        if row is not None and all(row["id"] != item["id"] for item in recipients):
            recipients.append(row)
    return recipients


def _ensure_campaign(conn: sqlite3.Connection, list_id: int, spec: dict) -> tuple[int, bool, int]:
    row = conn.execute(
        "SELECT id FROM campaigns WHERE list_id = ? AND subject = ?",
        (list_id, spec["subject"]),
    ).fetchone()
    if row is not None:
        return row["id"], False, 0

    days_ago_sent = spec["days_ago_sent"]
    sent_at = stamp(days_ago_sent) if days_ago_sent is not None else None
    cursor = conn.execute(
        "INSERT INTO campaigns (list_id, subject, from_name, body_markdown, sent_at, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            list_id,
            spec["subject"],
            spec["from_name"],
            spec["body"],
            sent_at,
            stamp((days_ago_sent or 1) + 1),
            sent_at or stamp(1),
        ),
    )
    campaign_id = int(cursor.lastrowid)
    if sent_at is None:
        return campaign_id, True, 0

    sends = 0
    for recipient in _campaign_recipients(conn, list_id, spec):
        email = recipient["email"]
        opened_days = spec["opened"].get(email)
        unsubscribed_days = spec["unsubscribed"].get(email)
        result = conn.execute(
            "INSERT OR IGNORE INTO campaign_sends (campaign_id, subscriber_id, email, "
            "open_token, unsubscribe_token, opened_at, open_count, unsubscribed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                campaign_id,
                recipient["id"],
                email,
                secrets.token_urlsafe(32),
                secrets.token_urlsafe(32),
                stamp(opened_days) if opened_days is not None else None,
                1 if opened_days is not None else 0,
                stamp(unsubscribed_days) if unsubscribed_days is not None else None,
                sent_at,
            ),
        )
        sends += result.rowcount

    # Keep the subscriber record consistent with the unsubscribe recorded above.
    for email, days in spec["unsubscribed"].items():
        conn.execute(
            "UPDATE subscribers SET status = 'unsubscribed', unsubscribed_at = ?, "
            "updated_at = ? WHERE list_id = ? AND lower(email) = lower(?)",
            (stamp(days), stamp(days), list_id, email),
        )
    return campaign_id, True, sends


def seed_database(conn: sqlite3.Connection) -> dict:
    """Create the demo account and its content. Safe to run repeatedly."""
    counts = {"lists": 0, "subscribers": 0, "campaigns": 0, "sends": 0}
    created_anything = False

    with transaction(conn):
        owner_id, user_created = _ensure_user(conn)
        created_anything = created_anything or user_created

        list_ids: dict[str, int] = {}
        for key, name, description in LIST_SPECS:
            list_id, created = _ensure_list(conn, owner_id, name, description)
            list_ids[key] = list_id
            counts["lists"] += int(created)
            created_anything = created_anything or created

        for key, email, name, status, joined, confirmed in SUBSCRIBER_SPECS:
            _, created = _ensure_subscriber(
                conn, list_ids[key], email, name, status, joined, confirmed
            )
            counts["subscribers"] += int(created)
            created_anything = created_anything or created

        for spec in CAMPAIGN_SPECS:
            _, created, sends = _ensure_campaign(conn, list_ids[spec["list"]], spec)
            counts["campaigns"] += int(created)
            counts["sends"] += sends
            created_anything = created_anything or created

    return {
        "created": created_anything,
        "counts": counts,
        "demo_email": DEMO_EMAIL,
        "demo_password": DEMO_PASSWORD,
    }
