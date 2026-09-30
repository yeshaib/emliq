import os
from pathlib import Path

HOME = Path(os.environ.get("EMLIQ_HOME", Path.home() / ".emliq"))
CREDENTIALS = HOME / "credentials.json"
TOKEN = HOME / "token.json"
DB = HOME / "emliq.db"
ANTHROPIC_KEY = HOME / "anthropic_key"  # set from the Settings page (mode 600)

# gmail.modify: read metadata, label/archive/trash, send unsubscribe emails.
# gmail.settings.basic: create filters for "Block".
# Neither allows permanent deletion; trashed mail is purged by Gmail after 30 days.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]


def ensure_home():
    HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
