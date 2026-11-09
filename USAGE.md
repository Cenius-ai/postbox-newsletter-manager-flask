# Using Postbox Newsletter Manager

## Overview

This is **Postbox Newsletter Manager** — an HTTP API + web UI. This document covers the surface area you can use, with copy-pasteable examples for each entry point. For setup, see `INSTALL.md`.

## Quickstart

After completing the install steps in `INSTALL.md`:

```bash
flask --app app run --debug    # start the server
# in another terminal:
curl http://localhost:8000/health
```

## Endpoints

Every endpoint below was extracted from the source by the route scanner (Next.js / FastAPI / Flask / Django / Express).

| Method | Path | Source file |
|--------|------|-------------|
| `GET` | `/health` | `app/__init__.py` |
| `GET` | `/campaigns/<int:campaign_id>/edit` | `app/campaigns.py` |
| `GET` | `/campaigns/new` | `app/campaigns.py` |
| `GET` | `/confirm/<token>` | `app/public.py` |
| `GET` | `/lists/<int:list_id>/import` | `app/importer.py` |
| `GET` | `/login` | `app/auth.py` |
| `GET` | `/register` | `app/auth.py` |
| `GET` | `/unsubscribe/<token>` | `app/public.py` |

### curl examples

#### `GET /health`

```bash
curl http://localhost:8000/health
```

#### `GET /campaigns/<int:campaign_id>/edit`

```bash
curl http://localhost:8000/campaigns/<int1>/edit
```

#### `GET /campaigns/new`

```bash
curl http://localhost:8000/campaigns/new
```

#### `GET /confirm/<token>`

```bash
curl http://localhost:8000/confirm/<token>
```

#### `GET /lists/<int:list_id>/import`

```bash
curl http://localhost:8000/lists/<int1>/import
```

## Worked example

1. Boot the server (`flask --app app run --debug`).
2. Hit a smoke-test endpoint:

```bash
curl -sS http://localhost:8000/health
```

3. If you get a JSON / HTML response, the server is healthy. Inspect `.env` if it errors with an auth/config failure.

## Reference

### Entry points

_No explicit entry points declared in this project's manifests._

### Surface index (auto-extracted)

| Kind | Title | Source file |
|------|-------|-------------|
| route | `GET /health` | `app/__init__.py` |
| route | `/campaigns/<int:campaign_id>/edit` | `app/campaigns.py` |
| route | `/campaigns/new` | `app/campaigns.py` |
| route | `/confirm/<token>` | `app/public.py` |
| route | `/lists/<int:list_id>/import` | `app/importer.py` |
| route | `/login` | `app/auth.py` |
| route | `/register` | `app/auth.py` |
| route | `/unsubscribe/<token>` | `app/public.py` |

## Next steps

- Read [INSTALL.md](./INSTALL.md) if anything in the Quickstart didn't work.
- Inspect `.env.example` for the full list of environment variables this project understands.
- See [README.md](./README.md) for the architecture diagram + feature list.
