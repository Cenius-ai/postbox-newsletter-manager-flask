"""SQLite access for Postbox.

The brief pins the persistence layer to the standard library ``sqlite3`` module,
so there is no ORM here: one connection per request on ``flask.g``, ``Row``
rows, foreign keys ON and WAL journaling so the send transaction and the CSV
import can write without blocking readers.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from flask import g

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
SCHEMA_PATH = PACKAGE_DIR / "schema.sql"

DEFAULT_DATABASE_URL = "sqlite:///instance/postbox.db"


def database_path() -> Path:
    """Resolve the SQLite file, relative to the project root by default."""
    raw = (os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL).strip()
    if raw.startswith("sqlite:///"):
        raw = raw[len("sqlite:///") :]
    elif "://" in raw:
        raise RuntimeError(
            "Postbox stores its data in SQLite; set DATABASE_URL to "
            "sqlite:///relative/path.db (got %r)." % raw
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or database_path()
    # sqlite3 will not create directories for us, and a fresh clone has none.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def get_db() -> sqlite3.Connection:
    """The request-scoped connection."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(exception: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    """Create every table/index that does not exist yet (idempotent)."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit write transaction; rolls back on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
