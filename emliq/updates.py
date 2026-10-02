"""Tell the user when a newer emliq release is out (never updates by itself).

At most once a day, emliq asks GitHub's public API for the project's latest release.
The request carries no data about the user or their mail, and can be turned off.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request

from . import __version__
from .db import get_meta, set_meta

REPO = "yeshaib/emliq"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
CHECK_EVERY = 24 * 3600


def parse(version):
    """'v0.8.0' or '0.8.0' -> (0, 8, 0); anything unparseable sorts lowest."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (version or "").strip())
    return tuple(map(int, m.groups())) if m else (0, 0, 0)


def enabled(conn):
    return get_meta(conn, "update_check", "on") == "on"


def set_enabled(conn, on):
    set_meta(conn, "update_check", "on" if on else "off")


def _fetch():
    req = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"emliq/{__version__}",
    })
    with urllib.request.urlopen(req, timeout=6) as resp:
        data = json.load(resp)
    return {
        "version": (data.get("tag_name") or "").lstrip("v"),
        "url": data.get("html_url"),
        "name": data.get("name"),
        "notes": (data.get("body") or "")[:4000],
        "published": data.get("published_at"),
    }


def status(conn, force=False, fetch=_fetch):
    """Latest-release info, refreshed at most daily (or now, with force)."""
    on = enabled(conn)
    checked = int(get_meta(conn, "update_checked_at", 0) or 0)
    latest = json.loads(get_meta(conn, "update_latest", "null") or "null")
    error = None
    if (on or force) and (force or time.time() - checked > CHECK_EVERY):
        try:
            latest = fetch()
            checked = int(time.time())
            set_meta(conn, "update_latest", json.dumps(latest))
            set_meta(conn, "update_checked_at", checked)
        except Exception as e:  # offline, rate limited, GitHub down: just try again later
            error = f"Couldn't check for updates: {getattr(e, 'reason', e)}"
    available = bool(latest and parse(latest["version"]) > parse(__version__))
    return {
        "current": __version__,
        "latest": latest,
        "available": available,
        "enabled": on,
        "checked_at": checked or None,
        "error": error,
        "commands": {
            "uv": f"uv tool install --reinstall https://github.com/{REPO}/archive/refs/tags/v{latest['version']}.zip" if latest else None,
            "docker": "git pull && docker compose up -d --build",
            "source": "git pull && uv pip install -e .",
        },
    }
