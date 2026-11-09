"""Values shared across the app: the demo identity, time format and token TTL."""

STAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# Double opt-in links expire after a week; the list page can reissue them.
CONFIRM_TOKEN_DAYS = 7

# The demo account the login page advertises. Seeded through the same hashing
# path as every other account.
DEMO_EMAIL = "cenius@cenius.ai"
DEMO_USERNAME = "cenius"
DEMO_PASSWORD = "cenius"
DEMO_DISPLAY_NAME = "Cenius Demo"
