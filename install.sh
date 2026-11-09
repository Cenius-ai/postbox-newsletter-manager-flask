#!/usr/bin/env bash
# Postbox Newsletter Manager installer.
#
#   bash install.sh
#
# Installs the project's Python dependencies, creates the SQLite schema, seeds
# the demo data and exits. It never starts the web server (that is run.py) and
# never installs a system package.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "error: python3 is required; install Python 3.11+ and re-run." >&2
  exit 1
fi

echo "==> Upgrading packaging tools"
"$PYTHON_BIN" -m pip install --upgrade --quiet pip setuptools wheel

echo "==> Installing project dependencies"
if ! "$PYTHON_BIN" -m pip install --quiet -r requirements.txt; then
  echo "==> Retrying with --user (no write access to system site-packages)"
  "$PYTHON_BIN" -m pip install --quiet --user -r requirements.txt
fi

if [ ! -f .env ]; then
  echo "==> Writing .env with a freshly generated SECRET_KEY"
  secret="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_hex(32))')"
  {
    printf 'DATABASE_URL=sqlite:///instance/postbox.db\n'
    printf 'SECRET_KEY=%s\n' "$secret"
  } > .env
fi

echo "==> Creating the SQLite schema and seeding demo data"
"$PYTHON_BIN" -m seed

echo "==> Verifying the application imports"
"$PYTHON_BIN" -c 'import app; print("app package imports cleanly")'

cat <<'EOF'

Install complete. Start Postbox with:

    python3 run.py

Then open http://127.0.0.1:5000 and sign in with the demo account:
    cenius@cenius.ai / cenius
EOF
