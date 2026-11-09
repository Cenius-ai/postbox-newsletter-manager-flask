"""WSGI entrypoint for production servers.

    gunicorn --bind 0.0.0.0:5000 wsgi:app
    flask --app wsgi:app run --host 0.0.0.0 --port 5000

``run.py`` remains the development entrypoint (`python3 run.py`); both share the
same application object, so the schema and demo data are ensured on either path.
"""

from run import app

__all__ = ["app"]
