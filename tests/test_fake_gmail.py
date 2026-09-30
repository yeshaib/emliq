"""End-to-end test of sync, bundles, actions, activity and AI categorizing against an
in-memory fake Gmail and a fake Claude. No network or Google account needed.

    python tests/test_fake_gmail.py [EMLIQ_HOME]
"""
import os, random, sys, tempfile
os.environ["EMLIQ_HOME"] = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()

from emliq import sync as syncmod
syncmod.time.sleep = lambda s: None  # no pacing in tests
from emliq.db import connect, get_meta
from emliq.sync import sync
from emliq import bundles, actions

random.seed(1)
SENDERS = [
    ("Amazon", "shipment-tracking@amazon.com", "amazon.com", "Your order #{n} has shipped", "<https://amazon.com/u/{n}>, <mailto:unsub@amazon.com?subject=unsub>", "List-Unsubscribe=One-Click"),
    ("LinkedIn", "messages-noreply@linkedin.com", "linkedin.com", "You appeared in {n} searches", "<mailto:u@linkedin.com>", None),
    ("=?UTF-8?B?Q2Fmw6k=?=", "news@cafe.fr", "cafe.fr", "Re: Newsletter {n}", "<https://cafe.fr/unsub>", None),
    ("Mom", "mom@gmail.com", None, "Dinner on {n}th?", None, None),
    ("GitHub", "notifications@github.com", "github.com", "[repo] PR #{n} merged", None, None),
]
CATS = ["CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS", "CATEGORY_PERSONAL", "CATEGORY_UPDATES"]

class Req:
    def __init__(self, fn): self.fn = fn
    def execute(self): return self.fn()

class Fake:
    def __init__(self, n):
        self.msgs = {}
        for i in range(n):
            s = random.randrange(len(SENDERS))
            name, addr, lid, subj, unsub, post = SENDERS[s]
            labels = [CATS[s]] + (["INBOX"] if random.random() < .7 else []) + (["UNREAD"] if random.random() < .5 else [])
            headers = [{"name": "From", "value": f"{name} <{addr}>"}, {"name": "Subject", "value": subj.format(n=i)}]
            if lid: headers.append({"name": "List-Id", "value": f"News <{lid}>"})
            if unsub: headers.append({"name": "List-Unsubscribe", "value": unsub.format(n=i)})
            if post: headers.append({"name": "List-Unsubscribe-Post", "value": post})
            self.msgs[f"m{i:05d}"] = {"id": f"m{i:05d}", "threadId": f"t{i}", "labelIds": labels,
                                      "sizeEstimate": random.choice([3000, 400_000, 2_000_000, 12_000_000]),
                                      "internalDate": str(1_600_000_000_000 + i * 86_400_000), "payload": {"headers": headers}}
        self.history, self.hid, self.sent, self.filters = [], 100, [], []
    # client surface
    def users(self): return self
    def messages(self): return self
    def history_(self): pass
    def settings(self): return self
    def filters_(self): pass
    def getProfile(self, userId): return Req(lambda: {"emailAddress": "Me@Example.com", "historyId": str(self.hid)})
    def list(self, userId, maxResults=500, pageToken=None, startHistoryId=None, fields=None, q=None):
        if startHistoryId is not None:
            return Req(lambda: {"history": [h for hid, h in self.history if hid > int(startHistoryId)]})
        ids = sorted(self.msgs, reverse=True)
        start = int(pageToken or 0)
        page = ids[start:start + maxResults]
        def fn():
            r = {"messages": [{"id": i} for i in page]}
            if start + maxResults < len(ids): r["nextPageToken"] = str(start + maxResults)
            return r
        r = Req(fn); r.token = start + maxResults; return r
    def list_next(self, req, resp):
        return self.list("me", pageToken=resp["nextPageToken"]) if "nextPageToken" in resp else None
    def get(self, userId, id, **kw):
        self.get_kwargs = kw  # privacy test below checks what sync asks for
        return ("get", id)
    def new_batch_http_request(self, callback=None):
        fake = self
        class B:
            def __init__(s): s.items = []
            def add(s, req, request_id=None): s.items.append((req, request_id))
            def execute(s):
                from googleapiclient.errors import HttpError
                class R: status = 404; reason = "nf"
                for (kind, mid), rid in s.items:
                    if kind == "trash":
                        fake._mod([mid], ["TRASH"], []); continue
                    if mid in fake.msgs: callback(rid, fake.msgs[mid], None)
                    else: callback(rid, None, HttpError(R(), b"not found"))
        return B()
    def _mod(self, ids, add, remove):
        self.hid += 1
        for i in ids:
            m = self.msgs[i]; m["labelIds"] = sorted((set(m["labelIds"]) | set(add)) - set(remove))
            self.history.append((self.hid, {"labelsAdded": [{"message": {"id": i, "labelIds": m["labelIds"]}}]}))
    def batchModify(self, userId, body):
        assert len(body["ids"]) <= 1000
        return Req(lambda: self._mod(body["ids"], body.get("addLabelIds", []), body.get("removeLabelIds", [])))
    def trash(self, userId, id): return ("trash", id)
    def send(self, userId, body): return Req(lambda: self.sent.append(body))
    def create(self, userId, body): return Req(lambda: self.filters.append(body))

fake = Fake(2500)
# users().history() / settings().filters() resolve back to the fake
class Users:
    def __getattr__(s, k):
        if k == "history": return lambda: fake
        if k == "filters": return lambda: fake
        return getattr(fake, k)
fake.users = lambda: Users()
Users.settings = lambda s: Users()
fake.settings = lambda: Users()

conn = connect()
sync(conn, fake)
st = bundles.stats(conn)
print("stats after full sync", st, "email", get_meta(conn, "email"))

# ---- privacy: headers only, never message content
kw = fake.get_kwargs
assert kw["format"] == "metadata", kw
assert not any(x in kw["fields"] for x in ("snippet", "raw", "body", "parts")), kw["fields"]
assert set(kw["metadataHeaders"]) <= {"From", "Subject", "List-Id", "List-Unsubscribe", "List-Unsubscribe-Post"}
cols = {r[1] for r in conn.execute("pragma table_info(messages)")}
assert not cols & {"body", "snippet", "content", "html", "text", "raw", "attachments"}, cols
from emliq.sync import _store, ContentNotAllowed
try:
    _store(conn, {"id": "x", "snippet": "secret text", "payload": {"headers": []}}); raise AssertionError("stored content")
except ContentNotAllowed:
    pass
try:
    _store(conn, {"id": "x", "payload": {"headers": [], "parts": [{"body": {"data": "c2VjcmV0"}}]}}); raise AssertionError("stored body")
except ContentNotAllowed:
    pass
print("PRIVACY OK")
assert st["total"] == 2500 and st["fetched"] == 2500

for view in bundles.VIEWS:
    rows = bundles.list_bundles(conn, view, "all")
    print(view, [(r["key"], r["label"], r["n"], r["can_unsubscribe"]) for r in rows[:6]])

# decode check
assert any(r["label"] == "Café" for r in bundles.list_bundles(conn, "sender", "all"))
# subject normalization bundles "Your order #N" together
subj = bundles.list_bundles(conn, "subject", "all")
assert subj[0]["n"] > 100, subj[:3]

# archive linkedin in inbox
before = bundles.stats(conn)["inbox"]
n = actions.apply(conn, fake, "sender", "messages-noreply@linkedin.com", "inbox", "archive")
after = bundles.stats(conn)["inbox"]
print("archived", n, before, "->", after); assert before - after == n
assert all("INBOX" not in m["labelIds"] for m in fake.msgs.values() if "linkedin" in m["payload"]["headers"][0]["value"])

# trash github (>1000 -> chunking)
n = actions.apply(conn, fake, "domain", "github.com", "all", "trash")
print("trashed", n)
assert not bundles.bundle_ids(conn, "domain", "github.com", "all")

# unsubscribe: amazon has one-click; stub the POST
calls = []
actions._one_click = lambda url: calls.append(url)
print(actions.unsubscribe(conn, fake, "sender", "shipment-tracking@amazon.com", "all"), calls)
print(actions.unsubscribe(conn, fake, "sender", "messages-noreply@linkedin.com", "all"), len(fake.sent))
print(actions.unsubscribe(conn, fake, "sender", "news@cafe.fr", "all"))
print(actions.unsubscribe(conn, fake, "sender", "mom@gmail.com", "all"))

# block list
print(actions.block(conn, fake, "list", "cafe.fr", "all"), fake.filters[-1])

# incremental sync picks up label changes & new/deleted mail
fake.msgs["m99999"] = dict(fake.msgs["m00000"], id="m99999")
fake.hid += 1; fake.history.append((fake.hid, {"messagesAdded": [{"message": {"id": "m99999"}}]}))
gone = next(i for i in fake.msgs if i != "m99999")
del fake.msgs[gone]; fake.hid += 1; fake.history.append((fake.hid, {"messagesDeleted": [{"message": {"id": gone}}]}))
conn2 = connect()
sync(conn2, fake)
assert conn2.execute("select fetched from messages where id='m99999'").fetchone()[0] == 1
assert conn2.execute("select count(*) from messages where id=?", (gone,)).fetchone()[0] == 0
print("incremental ok", bundles.stats(conn2))

# one-click SSRF guard
import emliq.actions as A, importlib; importlib.reload(A)
try: A._one_click("https://127.0.0.1/x"); print("FAIL no guard")
except ValueError as e: print("guard ok:", e)
print("ALL OK")

# query sync + parallel workers: new unread message outside the cache gets loaded, nothing dropped
fake.msgs["m88888"] = dict(fake.msgs["m00001"], id="m88888", labelIds=["INBOX", "UNREAD"])
before = conn2.execute("select count(*) from messages").fetchone()[0]
sync(conn2, fake, query="is:unread", make_service=lambda: fake)
after = conn2.execute("select count(*), sum(fetched=0) from messages").fetchone()
print("query sync", before, "->", tuple(after)); assert after[0] >= before and after[1] == 0
assert conn2.execute("select unread from messages where id='m88888'").fetchone()[0] == 1
print("QUERY OK")

# bulk: archive two bundles at once, unsubscribe many with mixed outcomes
keys = ["shipment-tracking@amazon.com", "mom@gmail.com"]
expect = sum(len(bundles.bundle_ids(conn2, "sender", k, "inbox")) for k in keys)
n = actions.apply_many(conn2, fake, "sender", keys, "inbox", "archive")
assert n == expect and not any(bundles.bundle_ids(conn2, "sender", k, "inbox") for k in keys), (n, expect)
actions._one_click = lambda url: None
res = actions.unsubscribe_many(conn2, fake, "sender", ["shipment-tracking@amazon.com", "news@cafe.fr", "mom@gmail.com"], "all")
print("bulk unsub", [(r["key"], r["method"]) for r in res])
assert [r["method"] for r in res] == ["one-click", "link", "none"]
print("BULK OK")

# ---- pagination
from emliq import analytics, ai
p1 = bundles.list_bundles(conn2, "subject", "all", page=1, per_page=2)
p2 = bundles.list_bundles(conn2, "subject", "all", page=2, per_page=2)
tot = bundles.count_bundles(conn2, "subject", "all")
assert len(p1) == 2 and p1[0]["key"] != p2[0]["key"] and tot["bundles"] >= 3, (p1, p2, tot)
print("pages ok", tot)

# ---- activity log from earlier actions
summ = analytics.summary(conn2)
print("activity", summ)
assert summ["archived"] > 0 and summ["unsubscribed"] >= 2 and summ["filters"] == 1
tl = analytics.timeline(conn2, 1, 15)
assert tl["total"] >= 5 and tl["items"][0]["ts"] >= tl["items"][-1]["ts"]
assert len(analytics.daily(conn2)) == 30 and analytics.history(conn2)

# ---- AI categorization with a fake Claude
import json as _json
from types import SimpleNamespace as NS
class FakeClaude:
    def __init__(self): self.calls = 0; self.beta = NS(messages=NS(create=self.create))
    def create(self, **kw):
        self.calls += 1
        assert kw["model"] == "claude-opus-5-5" and kw["fallbacks"] == "default"
        assert kw["output_config"]["format"]["type"] == "json_schema"
        senders = _json.loads(kw["messages"][0]["content"])
        res = [{"id": s["id"], "category": "Newsletters" if s["mailing_list"] else "Personal",
                "action": "unsubscribe" if s["mailing_list"] else "keep", "reason": "test"} for s in senders]
        return NS(stop_reason="end_turn", model=kw["model"],
                  content=[NS(type="thinking", thinking=""), NS(type="text", text=_json.dumps({"results": res}))])
fc = FakeClaude()
prog = syncmod.Progress()
out = ai.run(conn2, prog, client=fc)
print("ai", out, prog.snapshot())
cats = dict(conn2.execute("select from_email, action from sender_categories").fetchall())
assert cats["news@cafe.fr"] == "unsubscribe" and cats["mom@gmail.com"] == "keep", cats
assert ai.pending_senders(conn2) == []
ov = bundles.ai_overview(conn2, "all"); print("ai overview", ov)
unsub = bundles.list_bundles(conn2, "sender", "all", ai_action="unsubscribe")
assert unsub and all(r["ai_action"] == "unsubscribe" for r in unsub)
aiv = bundles.list_bundles(conn2, "ai", "all")
assert {r["key"] for r in aiv} <= set(ai.CATEGORIES)
print("AI OK")
