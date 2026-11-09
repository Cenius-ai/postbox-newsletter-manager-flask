"""Sessions, CSRF, route protection and response hardening.

One place owns the auth rules: :func:`enforce_access_rules` loads the signed-in
user, enforces the (short, documented) public allowlist for every other route
and verifies the session CSRF token on every state-changing request.
"""

from __future__ import annotations

import functools
import secrets
import time
from typing import Callable

from flask import (
    abort,
    current_app,
    flash,
    g,
    redirect,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

CSRF_SESSION_KEY = "csrf_token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# The only routes that work without a session. Everything else requires login,
# enforced centrally so a newly added route can never be accidentally public.
PUBLIC_ENDPOINTS = {
    "static",
    "health",
    "auth.login",
    "auth.register",
    "public.confirm",
    "public.unsubscribe",
    "tracking.pixel",
}

# Used to keep the failed-login path the same cost whether or not the account
# exists, so response timing does not reveal registered addresses.
_DUMMY_PASSWORD_HASH = generate_password_hash("postbox-timing-equaliser")


class RateLimiter:
    """A small fixed-window limiter (single process, in-memory).

    Postbox runs as one process against one SQLite file, so an in-process
    counter is the whole story; the map is pruned so it cannot grow unbounded.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[tuple[str, int], int] = {}

    def allow(self, key: str) -> bool:
        window = int(time.time() // self.window_seconds)
        if len(self._hits) > 2048:
            self._hits = {k: v for k, v in self._hits.items() if k[1] >= window}
        bucket = (key, window)
        self._hits[bucket] = self._hits.get(bucket, 0) + 1
        return self._hits[bucket] <= self.limit


def login_limiter() -> RateLimiter:
    """One limiter per application instance (so restarts start clean)."""
    limiter = current_app.extensions.get("postbox_login_limiter")
    if limiter is None:
        limiter = RateLimiter(limit=20, window_seconds=60)
        current_app.extensions["postbox_login_limiter"] = limiter
    return limiter


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def burn_password_check(password: str) -> None:
    """Spend the same time a real verification would (no user enumeration)."""
    verify_password(_DUMMY_PASSWORD_HASH, password)


def csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def start_session(user_id: int) -> None:
    """Rotate the session on privilege change and keep the CSRF token fresh."""
    session.clear()
    session["user_id"] = user_id
    session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
    session.permanent = True


def safe_redirect_target(candidate: str | None, fallback: str) -> str:
    """Only allow same-origin absolute paths as a post-login destination."""
    if not candidate or not candidate.startswith("/") or candidate.startswith("//"):
        return fallback
    return candidate


def login_required(view: Callable) -> Callable:
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapped


def load_logged_in_user() -> None:
    user_id = session.get("user_id")
    g.user = None
    if user_id is None:
        return
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        session.clear()
        return
    g.user = user


def _reject_csrf() -> None:
    abort(
        400,
        description=(
            "Your session token was missing or out of date. Reload the page and "
            "try again."
        ),
    )


def enforce_access_rules() -> None:
    """Central auth + CSRF gate, registered as an app-wide before_request."""
    endpoint = request.endpoint
    if endpoint is None:
        # Unknown URL: let the router's 404 handler answer.
        return

    load_logged_in_user()

    if endpoint not in PUBLIC_ENDPOINTS and g.get("user") is None:
        if request.method in SAFE_METHODS:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        flash("Sign in to continue.", "info")
        return redirect(url_for("auth.login"))

    if request.method in SAFE_METHODS:
        return

    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get(CSRF_SESSION_KEY)
    if not expected or not sent or not secrets.compare_digest(sent, expected):
        _reject_csrf()


def apply_security_headers(response):
    """CSP plus the usual hardening headers.

    Every script and stylesheet is served from /static, so the policy can stay
    strict: no inline script, no inline style, no remote origin.
    """
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; font-src 'self'; object-src 'none'",
    )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response
