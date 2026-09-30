from __future__ import annotations

import argparse
import threading
import webbrowser

from . import bundles
from .auth import gmail, login
from .db import connect
from .sync import Progress, sync


def main(argv=None):
    parser = argparse.ArgumentParser(prog="emliq", description="Bulk-clean your Gmail inbox.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("login", help="Sign in to Gmail (opens a browser)")
    p.add_argument("--no-browser", action="store_true", help="Print the sign-in URL instead of opening it")
    p.add_argument("--port", type=int, default=0, help="Port for Google's redirect (0 = random)")
    p.add_argument("--bind", default=None, help="Address to listen on for the redirect (0.0.0.0 in Docker)")

    p = sub.add_parser("sync", help="Download message headers into the local cache")
    p.add_argument("--full", action="store_true", help="Re-list every message instead of using history")
    p.add_argument("--max", type=int, help="Only sync the newest N messages (good for a first try)")
    p.add_argument("--query", help='Also load every message matching a Gmail search, e.g. "is:unread"')

    p = sub.add_parser("serve", help="Open the cleanup UI")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--host", default="127.0.0.1", help="Address to listen on (0.0.0.0 in Docker)")
    p.add_argument("--no-browser", action="store_true")

    p = sub.add_parser("demo", help="Try emliq with a made-up mailbox (no Google account needed)")
    p.add_argument("--port", type=int, default=8790)
    p.add_argument("--reset", action="store_true", help="Start over with fresh demo data")
    p.add_argument("--no-browser", action="store_true")

    p = sub.add_parser("bundles", help="Print the biggest bundles")
    p.add_argument("--view", choices=list(bundles.VIEWS), default="sender")
    p.add_argument("--scope", choices=["inbox", "unread", "all"], default="inbox")
    p.add_argument("--limit", type=int, default=25)

    args = parser.parse_args(argv)

    if args.cmd == "login":
        login(open_browser=not args.no_browser, port=args.port, bind_addr=args.bind)
        print("Signed in.")
    elif args.cmd == "sync":
        _sync_cli(args)
    elif args.cmd == "serve":
        from .web import app

        url = f"http://localhost:{args.port}/"
        print(f"emliq running at {url}  (Ctrl+C to stop)")
        if not args.no_browser:
            threading.Timer(1.0, webbrowser.open, (url,)).start()
        app.run(host=args.host, port=args.port, threaded=True)
    elif args.cmd == "demo":
        _demo_cli(args)
    elif args.cmd == "bundles":
        rows = bundles.list_bundles(connect(), args.view, args.scope, per_page=args.limit)
        for r in rows:
            print(f"{r['n']:>7}  {r['unread'] or 0:>6} unread  {(r['bytes'] or 0) / 1e6:>8.1f} MB  {r['label'] or r['key']}")


def _demo_cli(args):
    """Serve the demo in a child process with its own data folder, so real data is never touched."""
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    home = Path(os.environ.get("EMLIQ_DEMO_HOME", Path.home() / ".emliq-demo"))
    if args.reset and home.exists():
        shutil.rmtree(home)
    env = {**os.environ, "EMLIQ_HOME": str(home), "EMLIQ_DEMO": "1"}
    cmd = [sys.executable, "-m", "emliq.cli", "serve", "--port", str(args.port)]
    if args.no_browser:
        cmd.append("--no-browser")
    print(f"Demo mailbox (made-up data) in {home}")
    raise SystemExit(subprocess.call(cmd, env=env))


def _sync_cli(args):
    progress = Progress()
    stop = threading.Event()

    def report():
        last = None
        while not stop.wait(1):
            s = progress.snapshot()
            line = f"{s['phase']}: {s['done']}" + (f"/{s['total']}" if s["total"] else "")
            if line != last:
                print(line, flush=True)
                last = line

    t = threading.Thread(target=report, daemon=True)
    t.start()
    try:
        sync(connect(), gmail(), full=args.full, max_messages=args.max, query=args.query,
             progress=progress, make_service=gmail)
    finally:
        stop.set()
        t.join()
    print("Sync complete:", bundles.stats(connect()))


if __name__ == "__main__":
    main()
