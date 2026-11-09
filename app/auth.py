"""Accounts: demo login, self-service registration and logout."""

from __future__ import annotations

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .constants import DEMO_EMAIL, DEMO_PASSWORD
from .db import get_db
from .security import (
    burn_password_check,
    hash_password,
    login_limiter,
    safe_redirect_target,
    start_session,
    verify_password,
)
from .validation import clean_single_line, is_valid_email

bp = Blueprint("auth", __name__)

MIN_PASSWORD_LENGTH = 8
GENERIC_LOGIN_ERROR = "Email or password is incorrect."


def _find_user(identifier: str):
    return get_db().execute(
        "SELECT * FROM users WHERE lower(email) = lower(?) OR lower(username) = lower(?)",
        (identifier, identifier),
    ).fetchone()


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user") is not None:
        return redirect(url_for("dashboard.index"))

    identifier = ""
    errors: dict[str, str] = {}

    if request.method == "POST":
        identifier = clean_single_line(request.form.get("email"))
        password = request.form.get("password") or ""

        if not identifier:
            errors["email"] = "Enter the email address on your account."
        if not password:
            errors["password"] = "Enter your password."

        if not errors:
            if not login_limiter().allow(request.remote_addr or "local"):
                errors["form"] = (
                    "Too many sign-in attempts from this address. "
                    "Wait a minute and try again."
                )
            else:
                user = _find_user(identifier)
                if user is None:
                    burn_password_check(password)
                    errors["form"] = GENERIC_LOGIN_ERROR
                elif not verify_password(user["password_hash"], password):
                    errors["form"] = GENERIC_LOGIN_ERROR
                else:
                    start_session(int(user["id"]))
                    target = safe_redirect_target(
                        request.args.get("next"), url_for("dashboard.index")
                    )
                    return redirect(target, code=303)

    return render_template(
        "login.html",
        identifier=identifier,
        errors=errors,
        demo_email=DEMO_EMAIL,
        demo_password=DEMO_PASSWORD,
    )


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.get("user") is not None:
        return redirect(url_for("dashboard.index"))

    values = {"email": "", "display_name": ""}
    errors: dict[str, str] = {}

    if request.method == "POST":
        values["email"] = clean_single_line(request.form.get("email"))
        values["display_name"] = clean_single_line(request.form.get("display_name"))
        password = request.form.get("password") or ""

        if not values["email"]:
            errors["email"] = "Enter the email address you want to sign in with."
        elif not is_valid_email(values["email"]):
            errors["email"] = "That does not look like an email address."
        elif _find_user(values["email"]) is not None:
            errors["email"] = "An account with that email already exists."

        if len(password) < MIN_PASSWORD_LENGTH:
            errors["password"] = (
                f"Use at least {MIN_PASSWORD_LENGTH} characters so the account is "
                "not trivial to guess."
            )

        if not errors:
            cursor = get_db().execute(
                "INSERT INTO users (email, display_name, password_hash) VALUES (?, ?, ?)",
                (
                    values["email"].lower(),
                    values["display_name"] or None,
                    hash_password(password),
                ),
            )
            start_session(int(cursor.lastrowid))
            flash("Account created. Welcome to Postbox.", "success")
            return redirect(url_for("dashboard.index"), code=303)

    return render_template(
        "register.html",
        values=values,
        errors=errors,
        min_password=MIN_PASSWORD_LENGTH,
    )


@bp.post("/logout")
def logout():
    session.clear()
    flash("You are signed out.", "info")
    return redirect(url_for("auth.login"), code=303)
