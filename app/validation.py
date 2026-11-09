"""Small, shared input checks used by every form handler."""

from __future__ import annotations

import re

# Deliberately pragmatic: one @, no whitespace, a dot in the domain. Deeper
# verification belongs to the double opt-in click, not to a regex.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

MAX_EMAIL_LENGTH = 254
MAX_NAME_LENGTH = 120
MAX_SUBJECT_LENGTH = 140
MAX_LIST_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 280
MAX_FROM_NAME_LENGTH = 80


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value)) and len(value) <= MAX_EMAIL_LENGTH


def clean_single_line(value: str | None) -> str:
    """Trim and collapse internal runs of whitespace in a single-line field."""
    return " ".join((value or "").split())


def clean_text(value: str | None) -> str:
    """Trim a multi-line field, normalising CRLF but keeping line breaks."""
    return (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit]
