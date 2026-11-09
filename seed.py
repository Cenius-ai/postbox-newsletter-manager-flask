"""Seed the demo account and demo content.

    python3 -m seed

Creates the schema if needed, inserts the demo data idempotently, prints a
summary and exits. It never starts the web server.
"""

from __future__ import annotations

from app import create_app
from app.db import get_db
from app.seed import seed_database


def main() -> None:
    app = create_app(run_seed=False)  # schema only; this command runs the seed itself
    with app.app_context():
        report = seed_database(get_db())

    counts = report["counts"]
    if report["created"]:
        print(
            "Seeded demo data: "
            f"{counts['lists']} lists, {counts['subscribers']} subscribers, "
            f"{counts['campaigns']} campaigns, {counts['sends']} send rows."
        )
    else:
        print("Demo data already present — nothing to do.")

    print(f"Demo login: {report['demo_email']} / {report['demo_password']}")


if __name__ == "__main__":
    main()
