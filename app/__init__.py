"""Postbox Newsletter Manager application factory.

One Flask app, one blueprint per feature area, SQLite through the standard
library. The schema is created and the demo data seeded on the normal boot path
so a fresh clone opens on a populated app with no manual steps.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, Response, g, render_template

from .constants import STAMP_FORMAT
from .db import (
    DEFAULT_DATABASE_URL,
    PROJECT_ROOT,
    close_db,
    get_db,
    init_db,
)
from .seed import seed_database

# Development fallback for the session signing key. Deployments should set
# SECRET_KEY (install.sh generates one into .env); this only keeps a fresh
# clone bootable, and it is documented as insecure in the README.
DEV_SECRET_KEY = "cenius-dev-9f3a2c7b41d8e605"


def load_dotenv(path: Path | None = None) -> None:
    """Minimal KEY=VALUE loader so an install-generated .env is picked up."""
    env_path = path or (PROJECT_ROOT / ".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _humanize(value) -> str:
    """Relative timestamps, clamped so nothing ever reads "-2 days ago"."""
    if not value:
        return "—"
    try:
        moment = datetime.strptime(str(value)[:19], STAMP_FORMAT)
    except ValueError:
        return str(value)

    seconds = (datetime.utcnow() - moment).total_seconds()
    if seconds < 90:
        return "just now"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)} min ago"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)} h ago"
    days = hours / 24
    if days < 2:
        return "yesterday"
    if days < 30:
        return f"{int(days)} days ago"
    return moment.strftime("%d %b %Y").lstrip("0")


def _shortdate(value) -> str:
    if not value:
        return "—"
    try:
        moment = datetime.strptime(str(value)[:19], STAMP_FORMAT)
    except ValueError:
        return str(value)
    return moment.strftime("%d %b %Y").lstrip("0")


def create_app(*, run_seed: bool = True) -> Flask:
    load_dotenv()

    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
        static_url_path="/static",
    )
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or DEV_SECRET_KEY,
        DATABASE_URL=os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL,
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Never forced on: the app is demonstrated over plain http, where a
        # Secure cookie would silently drop every session.
        SESSION_COOKIE_SECURE=False,
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )

    # Imported here so the modules can import app.db without a cycle.
    from .auth import bp as auth_bp
    from .campaigns import bp as campaigns_bp
    from .dashboard import bp as dashboard_bp
    from .importer import bp as importer_bp
    from .lists import bp as lists_bp
    from .public import bp as public_bp
    from .security import apply_security_headers, csrf_token, enforce_access_rules
    from .sending import bp as sending_bp
    from .subscribers import bp as subscribers_bp
    from .tracking import bp as tracking_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(lists_bp)
    app.register_blueprint(subscribers_bp)
    app.register_blueprint(campaigns_bp)
    app.register_blueprint(sending_bp)
    app.register_blueprint(tracking_bp)
    app.register_blueprint(importer_bp)
    app.register_blueprint(public_bp)

    app.before_request(enforce_access_rules)
    app.after_request(apply_security_headers)
    app.teardown_appcontext(close_db)

    app.jinja_env.filters["humanize"] = _humanize
    app.jinja_env.filters["shortdate"] = _shortdate

    @app.get("/health")
    def health() -> Response:
        return Response("ok", mimetype="text/plain")

    @app.context_processor
    def inject_globals() -> dict:
        return {
            "csrf_token": csrf_token,
            "current_user": g.get("user"),
            "product_name": "Postbox Newsletter Manager",
        }

    @app.errorhandler(400)
    def bad_request(error):
        message = getattr(error, "description", None) or "That request could not be processed."
        return render_template("errors/400.html", message=message), 400

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):  # pragma: no cover - exercised only on real faults
        app.logger.exception("Unhandled error: %s", error)
        return render_template("errors/500.html"), 500

    with app.app_context():
        conn = get_db()
        init_db(conn)
        if run_seed:
            seed_database(conn)

    return app
