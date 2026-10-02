from __future__ import annotations

import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, redirect, request, send_from_directory
from googleapiclient.errors import HttpError

from . import __version__, actions, ai, analytics, ask, auth, bundles, ollama, updates
from .auth import NotAuthenticated
from .auth import gmail as _gmail
from .config import HOME
from .db import clear_mailbox, connect, get_meta, set_meta
from .sync import Progress, sync

STATIC = Path(__file__).parent / "static"
SCOPES = {"inbox", "unread", "all"}

# Hostnames the UI may be reached by. Anything else is refused, which blocks DNS
# rebinding. Add yours (comma-separated) if you put emliq behind a private hostname.
ALLOWED_HOSTS = {"127.0.0.1", "localhost"} | {
    h.strip() for h in os.environ.get("EMLIQ_ALLOWED_HOSTS", "").split(",") if h.strip()
}

DEMO = os.environ.get("EMLIQ_DEMO") == "1"

app = Flask(__name__)
progress = Progress()
ai_progress = Progress()
pull_progress = Progress()
PER_PAGE = {15, 30, 50, 100}


def gmail():
    if DEMO:
        raise ValueError("This is the demo mailbox, so nothing was changed. Run emliq with your own Gmail to clean up for real.")
    return _gmail()


if DEMO:  # fill the separate demo data folder on first start
    from . import demo as _demo

    _conn = connect()
    if not _conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]:
        _demo.seed(_conn)


@app.before_request
def guard():
    # Local-only tool: reject DNS-rebinding hosts and cross-site POSTs.
    if request.host.split(":")[0] not in ALLOWED_HOSTS:
        abort(403)
    if request.method == "POST":
        if not request.is_json:
            abort(415)
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            abort(403)


@app.errorhandler(NotAuthenticated)
def not_authenticated(e):
    return jsonify(error=str(e)), 401


@app.errorhandler(HttpError)
def gmail_error(e):
    return jsonify(error=f"Gmail API error {e.resp.status}: {e.reason}"), 502


@app.errorhandler(ValueError)
def bad_request(e):
    return jsonify(error=str(e)), 400


def _args(source):
    view = source.get("view", "sender")
    scope = source.get("scope", "inbox")
    if view not in bundles.VIEWS or scope not in SCOPES:
        raise ValueError("bad view or scope")
    return view, scope


@app.get("/")
def index():
    # Google sends the browser back here after the sign-in consent screen.
    if request.args.get("state") and (request.args.get("code") or request.args.get("error")):
        return _finish_sign_in()
    return send_from_directory(STATIC, "index.html")


def _finish_sign_in():
    from urllib.parse import quote

    if request.args.get("error"):
        return redirect("/?signin_error=" + quote("Sign-in was cancelled."))
    try:
        auth.finish_web_login(request.args["state"], request.args["code"])
        conn = connect()
        email = gmail().users().getProfile(userId="me").execute()["emailAddress"].lower()
        previous = get_meta(conn, "email")
        switched = bool(previous and previous != email)
        if switched:
            clear_mailbox(conn)  # never mix two accounts' mail
        set_meta(conn, "email", email)
        analytics.log(conn, "sign_in", label=email)
        return redirect("/?signed_in=" + ("switched" if switched else "1"))
    except Exception as e:
        return redirect("/?signin_error=" + quote(str(e)[:300]))


@app.get("/auth/start")
def auth_start():
    if DEMO:
        from urllib.parse import quote
        return redirect("/?signin_error=" + quote("Sign-in is off in the demo. Start emliq normally to use your own Gmail."))
    try:
        return redirect(auth.start_web_login(request.host_url))
    except ValueError as e:
        from urllib.parse import quote
        return redirect("/?signin_error=" + quote(str(e)))


@app.get("/api/auth")
def auth_status():
    if DEMO:
        return jsonify(signed_in=True, has_client=True, email=get_meta(connect(), "email"), demo=True)
    return jsonify(**auth.status(), email=get_meta(connect(), "email"))


@app.post("/api/auth/signout")
def auth_signout():
    body = request.get_json()
    conn = connect()
    email = get_meta(conn, "email")
    auth.sign_out(revoke=body.get("revoke", True))
    if body.get("clear_data"):
        clear_mailbox(conn)
    else:
        analytics.log(conn, "sign_out", label=email)
    return jsonify(**auth.status())


@app.post("/api/auth/client")
def auth_client():
    auth.save_client(request.get_json().get("json", ""))
    return jsonify(**auth.status())


@app.post("/api/ask")
def ask_question():
    body = request.get_json()
    return jsonify(ask.ask(connect(), body.get("question"), body.get("history")))


@app.get("/api/search")
def search():
    q = (request.args.get("q") or "").strip()
    _, scope = _args(request.args)
    if not q:
        raise ValueError("Type something to search for")
    conn = connect()
    senders = bundles.list_bundles(conn, "sender", scope, q=q, per_page=10)
    total_senders = bundles.count_bundles(conn, "sender", scope, q=q)
    total_messages, messages = bundles.search_messages(conn, q, scope, limit=50)
    return jsonify(senders=senders, total_senders=total_senders["bundles"], messages=messages,
                   total_messages=total_messages)


@app.get("/logo.svg")
def logo():
    return send_from_directory(STATIC, "logo.svg", mimetype="image/svg+xml")


def _changelog():
    """Parse CHANGELOG.md into [{version, date, changes: [...]}], newest first."""
    releases = []
    for line in (Path(__file__).parent / "CHANGELOG.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            version, _, date = line[3:].partition("—")
            releases.append({"version": version.strip(), "date": date.strip(), "changes": []})
        elif line.startswith("- ") and releases:
            releases[-1]["changes"].append(line[2:].strip())
    return releases


@app.get("/api/guide")
def guide():
    return jsonify(markdown=(Path(__file__).parent / "GUIDE.md").read_text(encoding="utf-8"))


@app.get("/api/update")
def update_status():
    return jsonify(updates.status(connect(), force=request.args.get("force") == "1"))


@app.post("/api/settings/updates")
def set_update_check():
    conn = connect()
    updates.set_enabled(conn, bool(request.get_json().get("enabled")))
    return jsonify(updates.status(conn))


@app.get("/api/version")
def version():
    return jsonify(version=__version__, releases=_changelog())


@app.get("/api/status")
def status():
    conn = connect()
    return jsonify(
        email=get_meta(conn, "email"),
        last_sync=get_meta(conn, "last_sync"),
        stats=bundles.stats(conn),
        sync=progress.snapshot(),
        ai=ai_progress.snapshot(),
        pull=pull_progress.snapshot(),
    )


@app.post("/api/sync")
def start_sync():
    if progress.snapshot()["running"]:
        return jsonify(error="Sync already running"), 409
    body = request.get_json()
    service = gmail()  # fail fast with 401 if not signed in
    progress.update(running=True, error=None, phase="starting", done=0, total=0, step=None, steps=None, estimate=False)

    def run():
        try:
            sync(connect(), service, full=bool(body.get("full")), query=body.get("query") or None,
                 progress=progress, make_service=gmail)
            progress.update(phase="done")
        except Exception as e:
            progress.update(phase="failed", error=str(e))
        finally:
            progress.update(running=False)

    threading.Thread(target=run, daemon=True).start()
    return jsonify(ok=True)


def _filters(source):
    emails = [e for e in (source.get("emails") or "").split(",") if e][:200] or None
    ai_category = source.get("ai_category") or None
    ai_action = source.get("ai_action") or None
    if ai_category and ai_category not in ai.CATEGORIES or ai_action and ai_action not in ai.ACTIONS:
        raise ValueError("bad AI filter")
    return {"ai_category": ai_category, "ai_action": ai_action, "emails": emails}


@app.get("/api/bundles")
def list_bundles():
    view, scope = _args(request.args)
    q = request.args.get("q") or None
    page = max(1, int(request.args.get("page", 1)))
    per_page = int(request.args.get("per_page", 15))
    if per_page not in PER_PAGE:
        raise ValueError("per_page must be one of 15, 30, 50, 100")
    conn, filters = connect(), _filters(request.args)
    rows = bundles.list_bundles(
        conn, view, scope, q=q, sort=request.args.get("sort") or None, page=page, per_page=per_page, **filters
    )
    totals = bundles.count_bundles(conn, view, scope, q=q, **filters)
    return jsonify(bundles=rows, page=page, per_page=per_page, total=totals["bundles"], total_messages=totals["messages"])


@app.get("/api/overview")
def overview():
    _, scope = _args(request.args)
    conn = connect()
    return jsonify(**bundles.overview(conn, scope), ai=bundles.ai_overview(conn, scope))


@app.get("/api/activity")
def activity():
    conn = connect()
    page = max(1, int(request.args.get("page", 1)))
    per_page = int(request.args.get("per_page", 15))
    if per_page not in PER_PAGE:
        raise ValueError("per_page must be one of 15, 30, 50, 100")
    return jsonify(
        summary=analytics.summary(conn),
        daily=analytics.daily(conn),
        history=analytics.history(conn),
        timeline=analytics.timeline(conn, page, per_page),
    )


@app.get("/api/settings")
def settings():
    conn = connect()
    cfg = ai.config(conn)
    return jsonify(
        anthropic=ai.key_status(),
        model=ai.MODEL,
        ai=cfg,
        ollama={**ollama.status(cfg["ollama_url"]), "recommended": ollama.RECOMMENDED},
        email=get_meta(conn, "email"),
        data_dir=str(HOME),
        categorized=conn.execute("SELECT COUNT(*) FROM sender_categories").fetchone()[0],
    )


@app.post("/api/settings/anthropic")
def set_anthropic_key():
    body = request.get_json()
    if body.get("remove"):
        ai.remove_key()
    else:
        ai.save_key(body.get("key"))
    return jsonify(anthropic=ai.key_status())


@app.post("/api/settings/ai")
def set_ai_settings():
    body = request.get_json()
    conn = connect()
    ai.save_config(conn, provider=body.get("provider"), ollama_model=body.get("ollama_model"),
                   ollama_url=body.get("ollama_url"))
    return jsonify(ai=ai.config(conn))


@app.post("/api/ollama/pull")
def ollama_pull():
    if pull_progress.snapshot()["running"]:
        return jsonify(error="A download is already running"), 409
    model = request.get_json().get("model")
    if not ollama.valid_model_name(model):
        raise ValueError("Invalid model name")
    url = ai.config(connect())["ollama_url"]
    pull_progress.update(running=True, error=None, phase="starting", done=0, total=0, model=model)

    def run():
        try:
            ollama.pull(url, model, pull_progress)
            conn = connect()
            ai.save_config(conn, provider="ollama", ollama_model=model)
            analytics.log(conn, "model_download", label=model, detail={"model": model})
            pull_progress.update(phase="done")
        except Exception as e:
            pull_progress.update(phase="failed", error=str(e))
        finally:
            pull_progress.update(running=False)

    threading.Thread(target=run, daemon=True).start()
    return jsonify(ok=True)


@app.get("/api/ai/estimate")
def ai_estimate():
    return jsonify(ai.estimate(connect()))


@app.post("/api/ai/categorize")
def ai_categorize():
    if ai_progress.snapshot()["running"]:
        return jsonify(error="Categorizing is already running"), 409
    ready, _, reason = ai.readiness(connect())
    if not ready:
        return jsonify(error=reason), 400
    ai_progress.start()

    def run():
        try:
            result = ai.run(connect(), ai_progress)
            ai_progress.update(phase="stopped" if result["stopped"] else "done", categorized=result["categorized"])
        except Exception as e:
            ai_progress.update(phase="failed", error=str(e))
        finally:
            ai_progress.update(running=False)

    threading.Thread(target=run, daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/ai/stop")
def ai_stop():
    if ai_progress.snapshot()["running"]:
        ai_progress.cancel()
    return jsonify(ai=ai_progress.snapshot())


@app.get("/api/messages")
def list_messages():
    view, scope = _args(request.args)
    return jsonify(messages=bundles.bundle_messages(connect(), view, request.args["key"], scope))


@app.post("/api/action")
def action():
    body = request.get_json()
    view, scope = _args(body)
    count = actions.apply(connect(), gmail(), view, body["key"], scope, body["action"])
    return jsonify(count=count)


@app.post("/api/bulk")
def bulk():
    body = request.get_json()
    view, scope = _args(body)
    keys = body.get("keys") or []
    if not isinstance(keys, list) or not keys or len(keys) > 1000:
        raise ValueError("keys must be a list of 1-1000 bundle keys")
    action, conn, service = body.get("action"), connect(), gmail()
    if action == "unsubscribe":
        return jsonify(results=actions.unsubscribe_many(conn, service, view, keys, scope))
    if action == "block":
        return jsonify(results=actions.block_many(conn, service, view, keys, scope, body.get("mode", "archive")))
    return jsonify(count=actions.apply_many(conn, service, view, keys, scope, action))


@app.post("/api/unsubscribe")
def unsubscribe():
    body = request.get_json()
    view, scope = _args(body)
    return jsonify(actions.unsubscribe(connect(), gmail(), view, body["key"], scope))


@app.post("/api/block")
def block():
    body = request.get_json()
    view, scope = _args(body)
    return jsonify(actions.block(connect(), gmail(), view, body["key"], scope, body.get("mode", "archive")))
