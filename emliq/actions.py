"""Bulk actions on a bundle: archive, mark read, trash, unsubscribe, block."""
from __future__ import annotations

import base64
import ipaddress
import socket
import urllib.request
from email.mime.text import MIMEText
from urllib.parse import parse_qs, unquote, urlsplit

from googleapiclient.errors import HttpError

from . import analytics, bundles
from .db import chunks, modify_labels

# action -> (labels to add, labels to remove)
LABEL_ACTIONS = {
    "archive": ((), ("INBOX",)),
    "read": ((), ("UNREAD",)),
    "archive_read": ((), ("INBOX", "UNREAD")),
    "trash": (("TRASH",), ()),
}


def apply(conn, service, view, key, scope, action, log=True):
    return apply_many(conn, service, view, [key], scope, action, log=log)


def bundle_label(conn, view, key):
    """A human name for a bundle, for the activity log."""
    if view in ("sender", "list"):
        row = conn.execute(
            f"SELECT from_name FROM messages WHERE {bundles.expr(view)} = ? ORDER BY date DESC LIMIT 1", (key,)
        ).fetchone()
        if row and row[0]:
            return row[0]
    return key


def _log(conn, action, view, keys, scope, messages=0, bytes=0, detail=None):
    one = len(keys) == 1
    analytics.log(
        conn, action, view=view, scope=scope, messages=messages, bytes=bytes,
        bundle=keys[0] if one else None,
        label=bundle_label(conn, view, keys[0]) if one else f"{len(keys)} bundles",
        detail=detail if detail is not None or one else {"keys": keys[:50]},
    )


def apply_many(conn, service, view, keys, scope, action, log=True):
    """Apply a label action to every message in several bundles at once."""
    if action not in LABEL_ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    ids = sorted({i for key in keys for i in bundles.bundle_ids(conn, view, key, scope)})
    add, remove = LABEL_ACTIONS[action]
    size = 0
    for chunk in chunks(ids, 1000):  # batchModify limit
        marks = ",".join("?" * len(chunk))
        size += conn.execute(f"SELECT COALESCE(SUM(size), 0) FROM messages WHERE id IN ({marks})", chunk).fetchone()[0]
        if action == "trash":
            _trash(service, chunk)
        else:
            body = {"ids": chunk, "addLabelIds": list(add), "removeLabelIds": list(remove)}
            service.users().messages().batchModify(userId="me", body=body).execute()
        modify_labels(conn, chunk, add, remove)
    if log and ids:
        _log(conn, action, view, keys, scope, messages=len(ids), bytes=size)
        analytics.snapshot(conn)
    return len(ids)


def unsubscribe_many(conn, service, view, keys, scope):
    """Unsubscribe from each bundle; one failure doesn't stop the rest."""
    results = []
    for key in keys:
        try:
            results.append({"key": key, **unsubscribe(conn, service, view, key, scope)})
        except Exception as e:
            results.append({"key": key, "method": "error", "message": str(e)})
    return results


def block_many(conn, service, view, keys, scope, mode="archive"):
    results = []
    for key in keys:
        try:
            results.append({"key": key, "ok": True, **block(conn, service, view, key, scope, mode)})
        except Exception as e:
            results.append({"key": key, "ok": False, "message": str(e)})
    return results


def _trash(service, ids):
    try:
        service.users().messages().batchModify(userId="me", body={"ids": ids, "addLabelIds": ["TRASH"]}).execute()
    except HttpError as e:
        if e.resp.status != 400:
            raise
        # Fall back to per-message trash if batchModify refuses the TRASH label.
        for chunk in chunks(ids, 50):
            batch = service.new_batch_http_request()
            for mid in chunk:
                batch.add(service.users().messages().trash(userId="me", id=mid))
            batch.execute()


# ---------------------------------------------------------------- unsubscribe


def unsubscribe_options(header):
    links = [part.strip().strip("<>").strip() for part in (header or "").split(",")]
    return (
        [l for l in links if l.lower().startswith(("https://", "http://"))],
        [l for l in links if l.lower().startswith("mailto:")],
    )


def unsubscribe(conn, service, view, key, scope):
    result = _unsubscribe(conn, service, view, key, scope)
    _log(conn, "unsubscribe", view, [key], scope, detail={"method": result["method"], "url": result.get("url")})
    return result


def _unsubscribe(conn, service, view, key, scope):
    msg = bundles.latest_in_bundle(conn, view, key, scope, require_unsubscribe=True)
    if not msg:
        return {"method": "none", "message": "No List-Unsubscribe header in this bundle."}
    urls, mailtos = unsubscribe_options(msg["list_unsubscribe"])
    one_click = "one-click" in (msg["list_unsubscribe_post"] or "").lower()

    # RFC 8058 one-click: a bare POST, no page to visit, no email sent.
    https = [u for u in urls if u.lower().startswith("https://")]
    if one_click and https:
        try:
            _one_click(https[0])
            return {"method": "one-click", "message": f"Unsubscribed from {msg['from_email']}."}
        except Exception as e:  # fall through to the other methods
            one_click_error = str(e)
    else:
        one_click_error = None

    if mailtos:
        to = _send_unsubscribe_email(service, mailtos[0])
        return {"method": "email", "message": f"Sent unsubscribe request to {to}."}
    if urls:
        return {"method": "link", "url": urls[0], "message": "Open the sender's unsubscribe page to finish."}
    return {"method": "none", "message": f"One-click unsubscribe failed: {one_click_error}"}


def _one_click(url):
    host = urlsplit(url).hostname or ""
    # Don't let an email header point us at something on the local network.
    for info in socket.getaddrinfo(host, 443):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f"refusing to POST to non-public address {ip}")
    req = urllib.request.Request(
        url,
        data=b"List-Unsubscribe=One-Click",
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "emliq/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 400:
            raise ValueError(f"HTTP {resp.status}")


def _send_unsubscribe_email(service, mailto):
    parts = urlsplit(mailto)
    to = unquote(parts.path)
    query = {k.lower(): v[0] for k, v in parse_qs(parts.query).items()}
    mime = MIMEText(query.get("body", "unsubscribe"))
    mime["To"] = to
    mime["Subject"] = query.get("subject", "unsubscribe")
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return to


# ---------------------------------------------------------------------- block

BLOCKABLE = {"sender", "domain", "list", "subject"}


def block(conn, service, view, key, scope, mode="archive"):
    """Create a Gmail filter for future mail, then apply the same action to the existing bundle."""
    if view not in BLOCKABLE:
        raise ValueError(f"Can't block a {view} bundle.")
    if view in ("sender", "domain"):
        criteria = {"from": key}
    elif view == "list":
        criteria = {"query": f"list:({key})"}
    else:
        latest = bundles.latest_in_bundle(conn, view, key, scope)
        criteria = {"subject": f'"{latest["subject"]}"'}

    if mode == "trash":
        action, existing = {"addLabelIds": ["TRASH"]}, "trash"
    else:
        action, existing = {"removeLabelIds": ["INBOX", "UNREAD"]}, "archive_read"
    service.users().settings().filters().create(
        userId="me", body={"criteria": criteria, "action": action}
    ).execute()
    count = apply(conn, service, view, key, scope, existing, log=False)
    _log(conn, "block", view, [key], scope, messages=count, detail={"criteria": criteria, "mode": mode})
    analytics.snapshot(conn)
    return {"criteria": criteria, "count": count}
