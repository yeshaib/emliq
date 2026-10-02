"""Activity log and mailbox snapshots for the Activity page. Stored locally only."""
from __future__ import annotations

import json
import time

# Actions that take messages out of the way, and how the Activity page names them.
CLEANUP_ACTIONS = ("trash", "archive", "archive_read", "read")


def log(conn, action, *, view=None, bundle=None, label=None, scope=None, messages=0, bytes=0, detail=None):
    conn.execute(
        """INSERT INTO activity(ts, action, view, bundle, label, scope, messages, bytes, detail)
           VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (int(time.time()), action, view, bundle, label, scope, messages or 0, bytes or 0,
         json.dumps(detail) if detail is not None else None),
    )
    conn.commit()


def snapshot(conn):
    """Record current mailbox totals; collapse snapshots taken within a minute of each other."""
    row = conn.execute(
        """SELECT COUNT(*), SUM(in_inbox), SUM(unread), SUM(size) FROM messages
           WHERE fetched = 1 AND hidden = 0"""
    ).fetchone()
    now = int(time.time())
    conn.execute("DELETE FROM snapshots WHERE ts > ?", (now - 60,))
    conn.execute("INSERT INTO snapshots VALUES(?, ?, ?, ?, ?)", (now, row[0], row[1] or 0, row[2] or 0, row[3] or 0))
    conn.commit()


def summary(conn):
    def total(where, col="messages"):
        return conn.execute(f"SELECT COALESCE(SUM({col}), 0) FROM activity WHERE {where}").fetchone()[0]

    first = conn.execute("SELECT MIN(ts) FROM activity").fetchone()[0]
    return {
        "trashed": total("action = 'trash'"),
        "archived": total("action IN ('archive', 'archive_read', 'block')"),
        "marked_read": total("action = 'read'"),
        "bytes_freed": total("action = 'trash'", "bytes"),
        "unsubscribed": conn.execute(
            "SELECT COUNT(*) FROM activity WHERE action = 'unsubscribe' AND json_extract(detail, '$.method') IN ('one-click', 'email', 'link')"
        ).fetchone()[0],
        "filters": conn.execute("SELECT COUNT(*) FROM activity WHERE action = 'block'").fetchone()[0],
        "since": first,
    }


def daily(conn, days=30):
    """Messages cleaned per day, oldest first, with zero-filled gaps."""
    start = int(time.time()) - days * 86400
    rows = dict(conn.execute(
        f"""SELECT date(ts, 'unixepoch', 'localtime') AS d, SUM(messages) FROM activity
            WHERE ts >= ? AND action IN ('trash', 'archive', 'archive_read', 'read', 'block', 'spam')
            GROUP BY d""",
        (start,),
    ).fetchall())
    out = []
    for i in range(days - 1, -1, -1):
        d = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
        out.append({"day": d, "messages": rows.get(d, 0)})
    return out


def history(conn, limit=200):
    rows = conn.execute(
        "SELECT ts, total, inbox, unread, bytes FROM snapshots ORDER BY ts DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def timeline(conn, page=1, per_page=15):
    total = conn.execute("SELECT COUNT(*) FROM activity").fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM activity ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page),
    ).fetchall()
    items = []
    for r in rows:
        item = dict(r)
        item["detail"] = json.loads(r["detail"]) if r["detail"] else None
        items.append(item)
    return {"items": items, "total": total, "page": page, "per_page": per_page}
