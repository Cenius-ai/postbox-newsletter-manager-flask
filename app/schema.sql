-- Postbox Newsletter Manager schema.
-- Safe to run against an existing database: every statement is guarded by
-- IF NOT EXISTS, so `python3 -m seed` and application boot can both call it.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT    NOT NULL UNIQUE,
    username      TEXT    UNIQUE,
    display_name  TEXT,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lists (
    id          INTEGER PRIMARY KEY,
    owner_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    description TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_lists_owner ON lists(owner_id);

CREATE TABLE IF NOT EXISTS subscribers (
    id                       INTEGER PRIMARY KEY,
    list_id                  INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    email                    TEXT    NOT NULL,
    name                     TEXT,
    status                   TEXT    NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'confirmed', 'unsubscribed')),
    confirm_token            TEXT    UNIQUE,
    confirm_token_expires_at TEXT,
    confirmed_at             TEXT,
    unsubscribed_at          TEXT,
    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_subscribers_list_email
    ON subscribers(list_id, lower(email));
CREATE INDEX IF NOT EXISTS ix_subscribers_list_status ON subscribers(list_id, status);

CREATE TABLE IF NOT EXISTS campaigns (
    id            INTEGER PRIMARY KEY,
    list_id       INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    subject       TEXT    NOT NULL,
    from_name     TEXT    NOT NULL,
    body_markdown TEXT    NOT NULL,
    sent_at       TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_campaigns_list ON campaigns(list_id);

CREATE TABLE IF NOT EXISTS campaign_sends (
    id                INTEGER PRIMARY KEY,
    campaign_id       INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    subscriber_id     INTEGER NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
    email             TEXT    NOT NULL,
    open_token        TEXT    NOT NULL UNIQUE,
    unsubscribe_token TEXT    NOT NULL UNIQUE,
    opened_at         TEXT,
    open_count        INTEGER NOT NULL DEFAULT 0,
    unsubscribed_at   TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_campaign_sends_recipient
    ON campaign_sends(campaign_id, subscriber_id);
CREATE INDEX IF NOT EXISTS ix_campaign_sends_campaign ON campaign_sends(campaign_id);
