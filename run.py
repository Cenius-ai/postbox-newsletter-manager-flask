"""Postbox Newsletter Manager entrypoint.

    python3 run.py

Binds 0.0.0.0 and honours $PORT (default 5000). The database schema and the
demo data are created on this boot path, so a fresh clone renders a populated
app immediately.
"""

from __future__ import annotations

import os

from app import create_app

app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Postbox Newsletter Manager listening on 0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
