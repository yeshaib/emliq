"""Mirror Gmail message metadata into SQLite.

First run lists every message id (cheap), then fetches headers for ids not yet
fetched, so an interrupted sync resumes where it stopped. Later runs use the
History API and only touch what changed.
"""
from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from email.header import decode_header, make_header
from email.utils import parseaddr

from googleapiclient.errors import HttpError

try:  # file locking differs between macOS/Linux and Windows
    import fcntl
except ImportError:
    fcntl = None
    import msvcrt

from . import analytics
from .config import HOME, ensure_home
from .db import chunks, get_meta, set_labels, set_meta

# Privacy: emliq only ever asks Gmail for these headers plus labels, size and date.
# format="metadata" plus this field mask means Gmail never sends message bodies,
# snippets or attachments; _store() refuses anything else as a second safeguard.
HEADERS = ["From", "Subject", "List-Id", "List-Unsubscribe", "List-Unsubscribe-Post"]
FIELDS = "id,threadId,labelIds,sizeEstimate,internalDate,payload/headers"
# messages.get costs 5 quota units and Gmail allows 15,000 units/user/minute.
# In practice parallel batches trip Gmail's rate limiter long before that, so
# fetch small, evenly spaced batches one at a time (bursts of 50 get throttled).
BATCH = 10
WORKERS = 1
PACE = 0.5
RETRYABLE = {403, 429, 500, 502, 503}


class Progress:
    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._state = {"running": False, "phase": "idle", "done": 0, "total": 0, "error": None}

    def start(self, **kw):
        """Mark a new run as started, clearing any earlier stop request."""
        self._cancel.clear()
        self.update(running=True, error=None, warning=None, stopping=False, phase="starting", done=0, total=0, **kw)

    def cancel(self):
        self._cancel.set()
        self.update(stopping=True)

    def cancelled(self):
        return self._cancel.is_set()

    def update(self, **kw):
        with self._lock:
            self._state.update(kw)

    def snapshot(self):
        with self._lock:
            return dict(self._state)


def sync(conn, service, full=False, max_messages=None, query=None, progress=None, make_service=None):
    """Sync the cache with Gmail.

    query: also load every message matching a Gmail search (e.g. "is:unread")
    on top of what's already cached, without dropping anything.
    make_service: builds a Gmail client per worker thread so headers can be
    fetched in parallel; without it fetching is sequential.
    """
    progress = progress or Progress()
    with _sync_lock():
        _sync(conn, service, full, max_messages, query, progress, make_service)


class SyncAlreadyRunning(RuntimeError):
    pass


class _sync_lock:
    """Cross-process lock so the CLI and web UI never sync at once and split the quota."""

    def __enter__(self):
        ensure_home()
        self.f = open(HOME / "sync.lock", "a+")
        try:
            if fcntl:
                fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.f.close()
            raise SyncAlreadyRunning("Another sync is already running; wait for it to finish.")
        return self

    def __exit__(self, *exc):
        if fcntl:
            fcntl.flock(self.f, fcntl.LOCK_UN)
        else:
            self.f.seek(0)
            msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
        self.f.close()


def _sync(conn, service, full, max_messages, query, progress, make_service):
    # Capture historyId before listing so changes made during the sync are picked up next time.
    profile = _with_retry(service.users().getProfile(userId="me").execute)
    set_meta(conn, "email", profile["emailAddress"].lower())
    history_id = get_meta(conn, "history_id")

    # Steps are numbered for the progress UI ("Step 1 of 2 · Finding messages").
    if query:
        steps = 3 if history_id else 2
        if history_id:
            progress.update(step=1, steps=steps)
            _incremental_or_skip(conn, service, history_id, progress)
        progress.update(step=steps - 1, steps=steps)
        _list_query(conn, service, query, max_messages, progress)
    elif history_id and not full and not max_messages:
        progress.update(step=1, steps=2)
        try:
            _incremental(conn, service, history_id, progress)
        except HttpError as e:
            if e.resp.status != 404:  # 404 = history too old, fall back to full
                raise
            _full(conn, service, None, progress, profile.get("messagesTotal"))
    else:
        progress.update(step=1, steps=2)
        _full(conn, service, max_messages, progress, profile.get("messagesTotal"))

    progress.update(step=progress.snapshot().get("steps", 2), estimate=False)
    fetched = _fetch_pending(conn, service, progress, make_service)
    set_meta(conn, "history_id", profile["historyId"])
    set_meta(conn, "last_sync", int(time.time()))
    analytics.log(conn, "sync", messages=fetched, detail={"query": query, "full": bool(full)})
    analytics.snapshot(conn)


def _full(conn, service, max_messages, progress, mailbox_total=None):
    gen = int(get_meta(conn, "gen", 0)) + 1
    listed = 0
    # Gmail's mailbox total (includes Spam/Trash, which aren't listed) is a good upper estimate.
    estimate = min(x for x in (mailbox_total, max_messages) if x) if (mailbox_total or max_messages) else 0
    progress.update(phase="listing", done=0, total=estimate, estimate=True)
    messages = service.users().messages()
    req = messages.list(userId="me", maxResults=500, fields="messages/id,nextPageToken")
    while req is not None:
        resp = _with_retry(req.execute)
        ids = [m["id"] for m in resp.get("messages", [])]
        if max_messages:
            ids = ids[: max_messages - listed]
        conn.executemany(
            "INSERT INTO messages(id, seen_gen) VALUES(?, ?) "
            "ON CONFLICT(id) DO UPDATE SET seen_gen = excluded.seen_gen",
            [(i, gen) for i in ids],
        )
        conn.commit()
        listed += len(ids)
        progress.update(done=listed, total=max(estimate, listed))
        if max_messages and listed >= max_messages:
            break
        req = messages.list_next(req, resp)
    progress.update(total=listed, estimate=False)
    # Anything not listed this round was deleted (or trashed) elsewhere.
    conn.execute("DELETE FROM messages WHERE seen_gen != ?", (gen,))
    set_meta(conn, "gen", gen)


def _list_query(conn, service, query, max_messages, progress):
    listed = 0
    estimate = _query_estimate(service, query)
    if max_messages:
        estimate = min(estimate or max_messages, max_messages)
    progress.update(phase=f"listing {query}", done=0, total=estimate, estimate=True)
    messages = service.users().messages()
    req = messages.list(userId="me", q=query, maxResults=500, fields="messages/id,nextPageToken,resultSizeEstimate")
    while req is not None:
        resp = _with_retry(req.execute)
        if not estimate and resp.get("resultSizeEstimate"):
            estimate = int(resp["resultSizeEstimate"])
        ids = [m["id"] for m in resp.get("messages", [])]
        if max_messages:
            ids = ids[: max_messages - listed]
        conn.executemany("INSERT OR IGNORE INTO messages(id) VALUES(?)", [(i,) for i in ids])
        conn.commit()
        listed += len(ids)
        progress.update(done=listed, total=max(estimate, listed))
        if max_messages and listed >= max_messages:
            break
        req = messages.list_next(req, resp)
    progress.update(total=listed, estimate=False)


def _query_estimate(service, query):
    """How many messages a search will list. Exact for is:unread (label count), else 0."""
    if query.strip().lower() == "is:unread":
        try:
            return int(_with_retry(service.users().labels().get(userId="me", id="UNREAD").execute)["messagesTotal"])
        except Exception:  # only an estimate for the progress bar; never fail a sync over it
            return 0
    return 0


def _incremental_or_skip(conn, service, history_id, progress):
    try:
        _incremental(conn, service, history_id, progress)
    except HttpError as e:
        if e.resp.status != 404:
            raise


def _incremental(conn, service, history_id, progress):
    progress.update(phase="checking changes", done=0, total=0)
    added, deleted, relabeled = set(), set(), {}
    history = service.users().history()
    req = history.list(userId="me", startHistoryId=history_id, maxResults=500)
    while req is not None:
        resp = _with_retry(req.execute)
        for h in resp.get("history", []):
            for item in h.get("messagesAdded", []):
                added.add(item["message"]["id"])
            for key in ("labelsAdded", "labelsRemoved"):
                for item in h.get(key, []):
                    relabeled[item["message"]["id"]] = item["message"].get("labelIds", [])
            for item in h.get("messagesDeleted", []):
                deleted.add(item["message"]["id"])
        progress.update(done=len(added | deleted | set(relabeled)))  # "N changes found"
        req = history.list_next(req, resp)

    for mid in deleted:
        conn.execute("DELETE FROM messages WHERE id = ?", (mid,))
    to_fetch = set(added)
    for mid, labels in relabeled.items():
        if mid in deleted or mid in added:
            continue
        exists = conn.execute("SELECT fetched FROM messages WHERE id = ?", (mid,)).fetchone()
        if exists and exists[0]:
            set_labels(conn, mid, labels)  # label change: no need to refetch headers
        else:
            to_fetch.add(mid)
    to_fetch -= deleted
    conn.executemany(
        "INSERT INTO messages(id, fetched) VALUES(?, 0) ON CONFLICT(id) DO UPDATE SET fetched = 0",
        [(i,) for i in to_fetch],
    )
    conn.commit()


def _fetch_pending(conn, service, progress, make_service=None):
    pending = [r[0] for r in conn.execute("SELECT id FROM messages WHERE fetched = 0")]
    progress.update(phase="fetching headers", done=0, total=len(pending))
    local = threading.local()

    def fetch(ids):
        svc = service
        if make_service:
            if not hasattr(local, "service"):
                local.service = make_service()
            svc = local.service
        started = time.monotonic()
        result = _batch_get(svc, ids)
        time.sleep(max(0.0, PACE - (time.monotonic() - started)))
        return result

    workers = WORKERS if make_service else 1
    queue, done, backoff = pending, 0, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while queue:
            # Dispatch one batch per worker at a time so we can stop the moment Gmail
            # starts rate-limiting, instead of burning quota on requests it will refuse.
            group, queue = queue[: workers * BATCH], queue[workers * BATCH :]
            retry_all = []
            for got, gone, retry in pool.map(fetch, chunks(group, BATCH)):
                for msg in got:
                    _store(conn, msg)
                conn.executemany("DELETE FROM messages WHERE id = ?", [(i,) for i in gone])
                conn.commit()
                done += len(got) + len(gone)
                progress.update(done=done)
                retry_all += retry
            if retry_all:
                queue = retry_all + queue
                backoff = backoff + 1 if len(retry_all) == len(group) else max(backoff, 1)
                if backoff > 8:
                    raise RuntimeError("Gmail kept rate-limiting; try again later (progress is saved).")
                progress.update(phase=f"rate limited, waiting {min(2 ** backoff, 64)}s")
                time.sleep(min(2 ** backoff, 64))
                progress.update(phase="fetching headers")
            else:
                backoff = 0
    return done


def _batch_get(service, ids):
    got, gone, retry, errors = [], [], [], []

    def callback(request_id, response, exception):
        if exception is None:
            got.append(response)
        elif isinstance(exception, HttpError) and exception.resp.status == 404:
            gone.append(request_id)
        elif isinstance(exception, HttpError) and exception.resp.status in RETRYABLE:
            retry.append(request_id)
        else:
            errors.append(exception)

    batch = service.new_batch_http_request(callback=callback)
    for mid in ids:
        batch.add(
            service.users().messages().get(
                userId="me", id=mid, format="metadata", metadataHeaders=HEADERS, fields=FIELDS
            ),
            request_id=mid,
        )
    _with_retry(batch.execute)
    if errors:
        raise errors[0]
    return got, gone, retry


def _with_retry(fn, attempts=6):
    for attempt in range(attempts):
        try:
            return fn()
        except HttpError as e:
            if e.resp.status not in RETRYABLE or attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)


class ContentNotAllowed(RuntimeError):
    pass


def _store(conn, msg):
    if "snippet" in msg or "raw" in msg or {"body", "parts"} & set(msg.get("payload", {})):
        raise ContentNotAllowed("Gmail returned message content; emliq only stores headers.")
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    name, addr = parseaddr(headers.get("from", ""))
    addr = addr.lower()
    subject = decode(headers.get("subject", ""))
    conn.execute(
        """UPDATE messages SET thread_id=?, fetched=1, from_name=?, from_email=?, from_domain=?,
           subject=?, subject_key=?, list_id=?, list_unsubscribe=?, list_unsubscribe_post=?,
           date=?, size=? WHERE id=?""",
        (
            msg.get("threadId"),
            decode(name) or addr,
            addr or None,
            addr.rpartition("@")[2] or None,
            subject,
            subject_key(subject),
            list_id(headers.get("list-id")),
            headers.get("list-unsubscribe"),
            headers.get("list-unsubscribe-post"),
            int(msg.get("internalDate", 0)),
            int(msg.get("sizeEstimate", 0)),
            msg["id"],
        ),
    )
    set_labels(conn, msg["id"], msg.get("labelIds", []))


def decode(value):
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return (value or "").strip()


_REPLY_PREFIX = re.compile(r"^\s*((re|fwd?|aw|sv|antw)\s*(\[\d+\])?\s*:\s*)+", re.I)
_DIGITS = re.compile(r"\d+")


def subject_key(subject):
    """Normalise a subject so 'Your order #123' and 'Your order #456' bundle together."""
    s = _REPLY_PREFIX.sub("", subject or "")
    s = _DIGITS.sub("#", s)
    s = " ".join(s.lower().split())[:200]
    return s or None


def list_id(value):
    if not value:
        return None
    m = re.search(r"<([^>]+)>", value)
    return (m.group(1) if m else value).strip().lower() or None
