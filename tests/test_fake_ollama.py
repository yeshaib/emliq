"""Local-AI test: categorizing via a fake Ollama server (downloads, schema-constrained chat,
models without thinking support, malformed rows). Run after test_fake_gmail.py on a copy
of its data folder; tests/run_tests.py does that for you."""
import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
home = sys.argv[1]
os.environ["EMLIQ_HOME"] = home
calls = {"chat": 0, "think_rejected": 0}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, obj, code=200):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/version": return self._json({"version": "fake"})
        if self.path == "/api/tags": return self._json({"models": [{"name": "tiny:1b", "size": 123}]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/pull":
            self.send_response(200); self.end_headers()
            for ev in [{"status": "pulling manifest"}, {"status": "downloading", "digest": "a", "total": 100, "completed": 50},
                       {"status": "downloading", "digest": "a", "total": 100, "completed": 100}, {"status": "success"}]:
                self.wfile.write((json.dumps(ev) + "\n").encode())
            return
        if self.path == "/api/chat":
            calls["chat"] += 1
            if "think" in body:  # simulate a model without thinking support
                calls["think_rejected"] += 1
                return self._json({"error": "model does not support thinking"}, 400)
            assert body["format"]["type"] == "object" and body["options"]["temperature"] == 0
            senders = json.loads(body["messages"][1]["content"])
            res = [{"id": s["id"], "category": "Newsletters" if s["mailing_list"] else "Personal",
                    "action": "unsubscribe" if s["mailing_list"] else "keep", "reason": "local"} for s in senders]
            res.append({"id": 999, "category": "Bogus", "action": "explode", "reason": "bad row"})  # must be ignored
            return self._json({"message": {"content": json.dumps({"results": res})}, "done_reason": "stop"})

srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_port}"

from emliq import ai, ollama, sync as syncmod
from emliq.db import connect
conn = connect()
conn.execute("DELETE FROM sender_categories"); conn.commit()
ai.save_config(conn, provider="ollama", ollama_url=url)
print("not ready yet:", ai.readiness(conn))
p = syncmod.Progress(); ollama.pull(url, "tiny:1b", p); print("pull", p.snapshot())
assert p.snapshot()["done"] == 100 and p.snapshot()["total"] == 100
ai.save_config(conn, ollama_model="tiny:1b")
print("ready:", ai.readiness(conn), ai.estimate(conn)["cost_high"])
prog = syncmod.Progress()
out = ai.run(conn, prog)
print("run", out, "calls", calls)
rows = dict(conn.execute("select from_email, action from sender_categories").fetchall())
assert rows["mom@gmail.com"] == "keep" and rows["news@cafe.fr"] == "unsubscribe" and "Bogus" not in str(rows)
assert conn.execute("select model from sender_categories limit 1").fetchone()[0] == "tiny:1b"
assert calls["think_rejected"] >= 1
try: ai.save_config(conn, ollama_model="bad name; rm -rf"); print("FAIL")
except ValueError: print("bad model name rejected")
ai.save_config(conn, provider="claude")
print("OLLAMA OK")
