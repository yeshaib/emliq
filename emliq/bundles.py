"""Group cached messages into bundles (by sender, domain, list, subject, ...)."""
from __future__ import annotations

from .db import get_meta

_SIZE = """CASE
    WHEN size >= 10485760 THEN '1 over 10 MB'
    WHEN size >= 5242880 THEN '2 5-10 MB'
    WHEN size >= 1048576 THEN '3 1-5 MB'
    WHEN size >= 262144 THEN '4 256 KB-1 MB'
    ELSE '5 under 256 KB' END"""

_YEAR = "strftime('%Y', date / 1000, 'unixepoch')"
_AI = "(SELECT sc.category FROM sender_categories sc WHERE sc.from_email = messages.from_email)"

# view -> (grouping expression, display-label expression, default ORDER BY)
VIEWS = {
    "sender": ("from_email", "MAX(from_name)", "n DESC"),
    "domain": ("from_domain", "from_domain", "n DESC"),
    "list": ("list_id", "MAX(from_name)", "n DESC"),
    "subject": ("subject_key", "MAX(subject)", "n DESC"),
    "category": ("category", "category", "n DESC"),
    "year": (_YEAR, _YEAR, "key DESC"),
    "size": (_SIZE, "SUBSTR(" + _SIZE + ", 3)", "key ASC"),
    "ai": (_AI, _AI, "n DESC"),
}
SORTS = {
    "count": "n DESC",
    "size": "bytes DESC",
    "latest": "latest DESC",
    "unread": "unread DESC, n DESC",
}


def _where(conn, scope, q=None, ai_category=None, ai_action=None, emails=None):
    clauses = ["fetched = 1", "hidden = 0", "COALESCE(from_email, '') != :me"]
    params = {"me": get_meta(conn, "email", "")}
    if scope == "inbox":
        clauses.append("in_inbox = 1")
    elif scope == "unread":
        clauses.append("unread = 1")
    if q:
        clauses.append("(from_email LIKE :q OR from_name LIKE :q OR subject LIKE :q OR list_id LIKE :q)")
        params["q"] = f"%{q}%"
    if ai_category:
        clauses.append("from_email IN (SELECT from_email FROM sender_categories WHERE category = :ai_category)")
        params["ai_category"] = ai_category
    if ai_action:
        clauses.append("from_email IN (SELECT from_email FROM sender_categories WHERE action = :ai_action)")
        params["ai_action"] = ai_action
    if emails:
        names = [f"e{i}" for i in range(len(emails))]
        clauses.append(f"from_email IN ({', '.join(':' + n for n in names)})")
        params.update(dict(zip(names, emails)))
    return " AND ".join(clauses), params


def expr(view):
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}")
    return VIEWS[view][0]


def list_bundles(conn, view, scope="inbox", q=None, sort=None, page=1, per_page=None,
                 ai_category=None, ai_action=None, emails=None, limit=None):
    """One page of bundles plus totals across all pages."""
    group, label, default_sort = VIEWS[view]
    where, params = _where(conn, scope, q, ai_category, ai_action, emails)
    order = SORTS.get(sort, default_sort)
    per_page = per_page or limit or 1000
    grouped = f"""SELECT {group} AS key, {label} AS label, COUNT(*) AS n, SUM(unread) AS unread,
               SUM(in_inbox) AS inbox, SUM(size) AS bytes, MAX(date) AS latest,
               MAX(list_unsubscribe IS NOT NULL) AS can_unsubscribe
            FROM messages WHERE {where}
            GROUP BY key HAVING key IS NOT NULL"""
    rows = [dict(r) for r in conn.execute(
        f"{grouped} ORDER BY {order}, key LIMIT :limit OFFSET :offset",
        {**params, "limit": per_page, "offset": (max(page, 1) - 1) * per_page},
    ).fetchall()]
    if view in ("sender", "list", "domain") and rows:
        _attach_ai(conn, view, rows)
    return rows


def count_bundles(conn, view, scope="inbox", q=None, ai_category=None, ai_action=None, emails=None):
    group = VIEWS[view][0]
    where, params = _where(conn, scope, q, ai_category, ai_action, emails)
    row = conn.execute(
        f"""SELECT COUNT(*), COALESCE(SUM(n), 0) FROM (
              SELECT {group} AS key, COUNT(*) AS n FROM messages WHERE {where}
              GROUP BY key HAVING key IS NOT NULL)""",
        params,
    ).fetchone()
    return {"bundles": row[0], "messages": row[1]}


def _attach_ai(conn, view, rows):
    """Add Claude's category/suggestion to sender rows (for list/domain, the latest sender's)."""
    if view == "sender":
        emails = {r["key"]: r["key"] for r in rows}
    else:
        col = "list_id" if view == "list" else "from_domain"
        marks = ",".join("?" * len(rows))
        # SQLite returns the bare column (from_email) from the row holding MAX(date).
        emails = {r[0]: r[1] for r in conn.execute(
            f"""SELECT {col}, from_email, MAX(date) FROM messages WHERE {col} IN ({marks})
                GROUP BY {col}""",
            [r["key"] for r in rows],
        ).fetchall()}
    wanted = [e for e in emails.values() if e]
    if not wanted:
        return
    marks = ",".join("?" * len(wanted))
    ai = {r[0]: r for r in conn.execute(
        f"SELECT from_email, category, action, reason FROM sender_categories WHERE from_email IN ({marks})", wanted
    ).fetchall()}
    for r in rows:
        hit = ai.get(emails.get(r["key"]))
        if hit:
            r["ai_category"], r["ai_action"], r["ai_reason"] = hit[1], hit[2], hit[3]


def ai_overview(conn, scope):
    where, params = _where(conn, scope)
    per_sender = f"SELECT from_email, COUNT(*) AS n FROM messages WHERE {where} GROUP BY from_email"
    rows = conn.execute(
        f"""SELECT sc.category AS key, SUM(m.n) AS n, COUNT(*) AS senders
            FROM ({per_sender}) m JOIN sender_categories sc ON sc.from_email = m.from_email
            GROUP BY sc.category ORDER BY n DESC""",
        params,
    ).fetchall()
    actions = conn.execute(
        f"""SELECT sc.action AS key, SUM(m.n) AS n, COUNT(*) AS senders
            FROM ({per_sender}) m JOIN sender_categories sc ON sc.from_email = m.from_email
            GROUP BY sc.action""",
        params,
    ).fetchall()
    return {"categories": [dict(r) for r in rows], "actions": [dict(r) for r in actions]}


def bundle_ids(conn, view, key, scope):
    where, params = _where(conn, scope)
    rows = conn.execute(
        f"SELECT id FROM messages WHERE {where} AND {expr(view)} = :key", {**params, "key": key}
    ).fetchall()
    return [r[0] for r in rows]


def bundle_messages(conn, view, key, scope, limit=100):
    where, params = _where(conn, scope)
    rows = conn.execute(
        f"""SELECT id, thread_id, from_name, from_email, subject, date, size, unread, in_inbox
            FROM messages WHERE {where} AND {expr(view)} = :key ORDER BY date DESC LIMIT :limit""",
        {**params, "key": key, "limit": limit},
    ).fetchall()
    return [dict(r) for r in rows]


def latest_in_bundle(conn, view, key, scope, require_unsubscribe=False):
    where, params = _where(conn, scope)
    extra = " AND list_unsubscribe IS NOT NULL" if require_unsubscribe else ""
    row = conn.execute(
        f"SELECT * FROM messages WHERE {where} AND {expr(view)} = :key{extra} ORDER BY date DESC LIMIT 1",
        {**params, "key": key},
    ).fetchone()
    return dict(row) if row else None


def stats(conn):
    row = conn.execute(
        """SELECT COUNT(*) AS total, SUM(fetched) AS fetched,
                  SUM(CASE WHEN fetched = 1 AND hidden = 0 AND in_inbox = 1 THEN 1 ELSE 0 END) AS inbox,
                  SUM(CASE WHEN fetched = 1 AND hidden = 0 AND unread = 1 THEN 1 ELSE 0 END) AS unread
           FROM messages"""
    ).fetchone()
    return {k: row[k] or 0 for k in row.keys()}


def overview(conn, scope):
    """Headline numbers and chart data for the dashboard, within a scope."""
    where, params = _where(conn, scope)
    k = conn.execute(
        f"""SELECT COUNT(*) AS messages, SUM(unread) AS unread, SUM(in_inbox) AS inbox,
                   SUM(size) AS bytes, COUNT(DISTINCT from_email) AS senders,
                   SUM(list_unsubscribe IS NOT NULL) AS list_messages,
                   COUNT(DISTINCT CASE WHEN list_unsubscribe IS NOT NULL THEN from_email END) AS list_senders
            FROM messages WHERE {where}""",
        params,
    ).fetchone()
    years = conn.execute(
        f"""SELECT {_YEAR} AS key, COUNT(*) AS n FROM messages WHERE {where}
            GROUP BY key HAVING key IS NOT NULL ORDER BY key""",
        params,
    ).fetchall()
    categories = conn.execute(
        f"""SELECT COALESCE(category, 'other') AS key, COUNT(*) AS n FROM messages WHERE {where}
            GROUP BY key ORDER BY n DESC""",
        params,
    ).fetchall()
    return {
        "kpis": {key: k[key] or 0 for key in k.keys()},
        "top_senders": list_bundles(conn, "sender", scope, limit=8),
        "years": [dict(r) for r in years],
        "categories": [dict(r) for r in categories],
    }


def search_messages(conn, q, scope="all", limit=50):
    """Messages whose subject or sender matches q, newest first (same fields as bundle_messages)."""
    where, params = _where(conn, scope, q)
    total = conn.execute(f"SELECT COUNT(*) FROM messages WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"""SELECT id, thread_id, from_name, from_email, subject, date, size, unread, in_inbox
            FROM messages WHERE {where} ORDER BY date DESC LIMIT :limit""",
        {**params, "limit": limit},
    ).fetchall()
    return total, [dict(r) for r in rows]
