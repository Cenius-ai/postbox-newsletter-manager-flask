# Installing Postbox Newsletter Manager

Postbox is a Flask application with a SQLite database. There is exactly one
package manager involved: **pip**, driven by the `requirements.txt` at the
project root. There is no JavaScript build step and no system package to
install.

## Prerequisites

- Python **3.11 or newer** (`python3 --version`)
- pip for that interpreter (`python3 -m pip --version`)
- A POSIX shell for `install.sh` (bash or dash both work)

That is the whole list. SQLite is part of the Python standard library, so no
database server, no Node, no Docker and no apt/apk packages are required.

## Step 1 — Install dependencies, create the schema and seed the demo data

```bash
bash install.sh
```

The script:

1. upgrades `pip`, `setuptools` and `wheel` for the interpreter it runs under,
2. installs `requirements.txt` (falls back to `--user` if site-packages is not
   writable, so it works as an unprivileged user),
3. writes a `.env` with a freshly generated `SECRET_KEY` if `.env` does not
   exist yet,
4. creates the SQLite schema and seeds the demo data,
5. verifies the application package imports, prints the start command and
   **exits**. It never starts the server.

It is safe to re-run: the schema is `CREATE ... IF NOT EXISTS` and the seed
checks before it inserts.

## Step 2 — Seed (its own step, also runnable on its own)

`install.sh` already ran this; run it again whenever you want the demo data
back, or on a machine where you installed the dependencies by hand:

```bash
python3 -m seed
```

It creates `instance/postbox.db` if missing, inserts the demo account
(`cenius@cenius.ai` / `cenius`), two lists, 15 subscribers across all three
states, two sent campaigns with opens and an unsubscribe recorded, and one
draft. Then it prints a summary and exits — it never binds the web port.

## Step 3 — Run in development

```bash
python3 run.py
```

The server binds `0.0.0.0` and reads `$PORT` (default `5000`), so
`PORT=8080 python3 run.py` moves it. Open <http://127.0.0.1:5000> and sign in
with `cenius@cenius.ai` / `cenius`.

Alternative WSGI entrypoints work too, because the package exposes a factory:

```bash
flask --app run:app run --host 0.0.0.0 --port 5000     # or an installed gunicorn:
gunicorn --bind 0.0.0.0:5000 run:app
```

## Step 4 — Tests (optional, needs no server running)

```bash
python3 -m pytest
```

Each test creates its own application instance backed by a temporary SQLite
file, so the suite never touches `instance/postbox.db`.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | `cenius-dev-9f3a2c7b41d8e605` | Signs the session cookie. The fallback keeps a fresh clone bootable and is **not** safe for production; `install.sh` generates a random one into `.env`. |
| `DATABASE_URL` | `sqlite:///instance/postbox.db` | SQLite file location. Relative paths resolve from the project root; the directory is created automatically. |
| `PORT` | `5000` | Port for `python3 run.py`. |

All three have working defaults: `cp .env.example .env` followed by
`python3 run.py` boots with zero edits, and so does starting with no `.env` at
all.

## Resetting the demo

```bash
rm -rf instance/
python3 -m seed
```

The next start recreates the schema and the demo content. Every table uses
`ON DELETE CASCADE`, so deleting a list through the UI also removes its
subscribers, campaigns and send rows.

## Troubleshooting

- **`Address already in use`** — another process holds the port. Stop it, or run
  `PORT=5001 python3 run.py`.
- **`ModuleNotFoundError: flask`** — run `python3 -m pip install -r requirements.txt`
  with the same interpreter that runs `run.py`.
- **Signed out immediately after signing in** — make sure the app is not behind
  a proxy that rewrites cookies, and that `SECRET_KEY` is stable between
  restarts (a random key per boot invalidates every session).
- **Nothing renders on a page** — the app sets a strict CSP
  (`default-src 'self'`); if you add inline `<script>` or `style="..."`
  attributes, move them into `static/` instead.
