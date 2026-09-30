import sqlite3

from .config import DB, ensure_home

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT,
    fetched INTEGER NOT NULL DEFAULT 0,
    seen_gen INTEGER NOT NULL DEFAULT 0,
    from_name TEXT,
    from_email TEXT,
    from_domain TEXT,
    subject TEXT,
    subject_key TEXT,
    list_id TEXT,
    list_unsubscribe TEXT,
    list_unsubscribe_post TEXT,
    date INTEGER,               -- ms since epoch (Gmail internalDate)
    size INTEGER,
    labels TEXT,                -- ",INBOX,UNREAD," for cheap LIKE matching
    in_inbox INTEGER NOT NULL DEFAULT 0,
    unread INTEGER NOT NULL DEFAULT 0,
    category TEXT,
    hidden INTEGER NOT NULL DEFAULT 0   -- trash, spam or draft
);
CREATE INDEX IF NOT EXISTS ix_fetched ON messages(fetched);
CREATE INDEX IF NOT EXISTS ix_from_email ON messages(from_email);
CREATE INDEX IF NOT EXISTS ix_from_domain ON messages(from_domain);
CREATE INDEX IF NOT EXISTS ix_list_id ON messages(list_id);
CREATE INDEX IF NOT EXISTS ix_subject_key ON messages(subject_key);
CREATE INDEX IF NOT EXISTS ix_date ON messages(date);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
-- Everything emliq does to the mailbox, for the Activity page.
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    action TEXT NOT NULL,
    view TEXT,
    bundle TEXT,
    label TEXT,
    scope TEXT,
    messages INTEGER NOT NULL DEFAULT 0,
    bytes INTEGER NOT NULL DEFAULT 0,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_activity_ts ON activity(ts);
-- Mailbox size over time.
CREATE TABLE IF NOT EXISTS snapshots (
    ts INTEGER PRIMARY KEY, total INTEGER, inbox INTEGER, unread INTEGER, bytes INTEGER
);
-- Claude's category and suggested action per sender.
CREATE TABLE IF NOT EXISTS sender_categories (
    from_email TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    model TEXT,
    ts INTEGER
);
"""

CATEGORIES = {
    "CATEGORY_PERSONAL": "primary",
    "CATEGORY_PROMOTIONS": "promotions",
    "CATEGORY_SOCIAL": "social",
    "CATEGORY_UPDATES": "updates",
    "CATEGORY_FORUMS": "forums",
}
HIDDEN_LABELS = {"TRASH", "SPAM", "DRAFT"}


def connect():
    ensure_home()
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


def label_columns(labels):
    """Derived columns for a set of Gmail label ids."""
    labels = set(labels)
    category = next((CATEGORIES[l] for l in labels if l in CATEGORIES), None)
    return {
        "labels": "," + ",".join(sorted(labels)) + ",",
        "in_inbox": int("INBOX" in labels),
        "unread": int("UNREAD" in labels),
        "category": category,
        "hidden": int(bool(labels & HIDDEN_LABELS)),
    }


def set_labels(conn, msg_id, labels):
    cols = label_columns(labels)
    conn.execute(
        "UPDATE messages SET labels=:labels, in_inbox=:in_inbox, unread=:unread, "
        "category=:category, hidden=:hidden WHERE id=:id",
        {**cols, "id": msg_id},
    )


def modify_labels(conn, ids, add=(), remove=()):
    """Mirror a Gmail label change locally so the UI updates without a re-sync."""
    add, remove = set(add), set(remove)
    for chunk in chunks(ids, 500):
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(f"SELECT id, labels FROM messages WHERE id IN ({marks})", chunk).fetchall()
        for row in rows:
            current = {l for l in (row["labels"] or "").split(",") if l}
            set_labels(conn, row["id"], (current | add) - remove)
    conn.commit()


def chunks(items, size):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i : i + size]


def clear_mailbox(conn):
    """Forget everything cached for the signed-in account (not settings)."""
    for table in ("messages", "sender_categories", "snapshots", "activity"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM meta WHERE key IN ('email', 'history_id', 'gen', 'last_sync')")
    conn.commit()
