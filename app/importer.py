"""CSV import with case-insensitive duplicate-address merging."""

from __future__ import annotations

import csv
import io
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, flash, render_template, request

from .constants import CONFIRM_TOKEN_DAYS, STAMP_FORMAT
from .db import get_db, transaction
from .lists import get_owned_list
from .security import login_required
from .validation import MAX_EMAIL_LENGTH, MAX_NAME_LENGTH, clean_single_line, is_valid_email

bp = Blueprint("importer", __name__)

MAX_ROWS = 5000
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_rows(text: str) -> tuple[list[dict], str | None]:
    """Split CSV text into normalised rows, or explain why it cannot be read."""
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return [], "The CSV was empty. Paste at least a header row and one address."

    header = [cell.strip().lower() for cell in rows[0]]
    if "email" not in header:
        return [], "The first row must be a header that includes an `email` column."

    email_index = header.index("email")
    name_index = header.index("name") if "name" in header else None
    data_rows = rows[1:]
    if not data_rows:
        return [], "The CSV only had a header row, so there was nothing to import."
    if len(data_rows) > MAX_ROWS:
        return [], (
            f"That file has {len(data_rows):,} rows; a single import accepts at most "
            f"{MAX_ROWS:,}. Split it and import in batches."
        )

    parsed = []
    for offset, row in enumerate(data_rows, start=2):
        email = clean_single_line(row[email_index]) if email_index < len(row) else ""
        name = (
            clean_single_line(row[name_index])
            if name_index is not None and name_index < len(row)
            else ""
        )
        parsed.append({"line": offset, "email": email, "name": name})
    return parsed, None


def _merge_rows(conn, list_id: int, rows: list[dict]) -> dict:
    """Insert new addresses and merge existing ones, in one transaction."""
    imported = 0
    updated = 0
    skipped: list[dict] = []

    with transaction(conn):
        for row in rows:
            email = row["email"]
            name = row["name"]

            if not email:
                skipped.append({"line": row["line"], "reason": "No email address in this row."})
                continue
            if len(email) > MAX_EMAIL_LENGTH:
                skipped.append(
                    {
                        "line": row["line"],
                        "reason": f"{email[:40]}… is longer than an email address can be.",
                    }
                )
                continue
            if not is_valid_email(email):
                skipped.append(
                    {"line": row["line"], "reason": f"“{email}” is not a valid email address."}
                )
                continue
            if len(name) > MAX_NAME_LENGTH:
                name = name[:MAX_NAME_LENGTH]

            existing = conn.execute(
                "SELECT id, status, name FROM subscribers WHERE list_id = ? "
                "AND lower(email) = lower(?)",
                (list_id, email),
            ).fetchone()

            if existing is None:
                expires = (datetime.utcnow() + timedelta(days=CONFIRM_TOKEN_DAYS)).strftime(
                    STAMP_FORMAT
                )
                conn.execute(
                    "INSERT INTO subscribers (list_id, email, name, status, confirm_token, "
                    "confirm_token_expires_at) VALUES (?, ?, ?, 'pending', ?, ?)",
                    (list_id, email, name or None, secrets.token_urlsafe(32), expires),
                )
                imported += 1
                continue

            # Merging must never undo a confirmation or an unsubscribe, and it
            # must never create a second row for an address already on the list.
            if name and name != (existing["name"] or ""):
                conn.execute(
                    "UPDATE subscribers SET name = ?, updated_at = datetime('now') "
                    "WHERE id = ?",
                    (name, existing["id"]),
                )
            updated += 1

    return {"imported": imported, "updated": updated, "skipped": skipped}


def _import_context(list_id: int) -> dict:
    return {"list_row": get_owned_list(list_id), "max_rows": MAX_ROWS}


@bp.route("/lists/<int:list_id>/import", methods=["GET", "POST"])
@login_required
def import_csv(list_id: int):
    context = _import_context(list_id)

    if request.method == "GET":
        return render_template(
            "lists/import.html", pasted="", errors=[], result=None, **context
        )

    pasted = request.form.get("csv_text") or ""
    errors: list[str] = []
    text = ""

    upload = request.files.get("csv_file")
    if upload is not None and upload.filename:
        raw = upload.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            errors.append(
                f"That file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
                "Split it and import in batches."
            )
        else:
            text = _decode(raw)
    if not text.strip():
        text = pasted

    if errors:
        return render_template(
            "lists/import.html", pasted=pasted, errors=errors, result=None, **context
        )

    if not text.strip():
        errors.append("Paste some CSV text or choose a .csv file first.")
        return render_template(
            "lists/import.html", pasted=pasted, errors=errors, result=None, **context
        )

    rows, parse_error = _parse_rows(text)
    if parse_error:
        return render_template(
            "lists/import.html", pasted=pasted, errors=[parse_error], result=None, **context
        )

    result = _merge_rows(get_db(), list_id, rows)
    flash(
        f"Import finished: {result['imported']} imported, {result['updated']} updated, "
        f"{len(result['skipped'])} skipped.",
        "success" if result["imported"] or result["updated"] else "info",
    )
    return render_template(
        "lists/import_result.html",
        pasted=pasted,
        errors=[],
        result=result,
        **context,
    )
