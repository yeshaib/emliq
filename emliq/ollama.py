"""Minimal client for a local Ollama server (https://ollama.com), stdlib only."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not DEFAULT_URL.startswith(("http://", "https://")):
    DEFAULT_URL = "http://" + DEFAULT_URL

# Shown in Settings as one-click downloads. Sizes from the Ollama registry.
RECOMMENDED = [
    {"name": "qwen3:14b", "size": "9.3 GB", "note": "Best accuracy that runs well on a 24 GB Mac"},
    {"name": "qwen3:8b", "size": "5.2 GB", "note": "About twice as fast, slightly less accurate"},
]
_MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9._\-/]*(:[a-z0-9._\-]+)?$")


class OllamaError(RuntimeError):
    pass


def _request(url, path, body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", e.reason)
        except Exception:
            msg = e.reason
        raise OllamaError(f"Ollama: {msg}") from None
    except (urllib.error.URLError, OSError) as e:
        raise OllamaError(f"Can't reach Ollama at {url} ({getattr(e, 'reason', e)}). Is it running?") from None


def status(url):
    try:
        with _request(url, "/api/version", timeout=3) as r:
            version = json.load(r).get("version")
        with _request(url, "/api/tags", timeout=5) as r:
            models = [{"name": m["name"], "size": m.get("size", 0)} for m in json.load(r).get("models", [])]
        return {"reachable": True, "version": version, "models": sorted(models, key=lambda m: m["name"])}
    except OllamaError as e:
        return {"reachable": False, "error": str(e), "models": []}


def valid_model_name(name):
    return bool(name and _MODEL_NAME.match(name))


def pull(url, model, progress):
    """Download a model, reporting bytes done/total across all layers."""
    if not valid_model_name(model):
        raise ValueError("Invalid model name")
    layers = {}
    with _request(url, "/api/pull", {"model": model, "stream": True}, timeout=60) as r:
        for line in r:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("error"):
                raise OllamaError(f"Ollama: {event['error']}")
            if event.get("digest") and event.get("total"):
                layers[event["digest"]] = (event.get("completed", 0), event["total"])
            done = sum(c for c, _ in layers.values())
            total = sum(t for _, t in layers.values())
            progress.update(phase=event.get("status", "downloading"), done=done, total=total)
            if event.get("status") == "success":
                return


def chat_json(url, model, system, user, schema, timeout=600):
    """One chat turn constrained to a JSON schema. Returns the parsed object."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        "think": False,  # reasoning models: skip thinking, this task doesn't need it
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    try:
        resp = _request(url, "/api/chat", body, timeout=timeout)
    except OllamaError as e:
        if "think" not in str(e):
            raise
        body.pop("think")  # model has no thinking mode
        resp = _request(url, "/api/chat", body, timeout=timeout)
    with resp as r:
        data = json.load(r)
    if data.get("done_reason") == "length":
        raise RuntimeError("response was cut off")
    return json.loads(data["message"]["content"])


def chat(url, body, timeout=600):
    """One /api/chat call (tools allowed). Returns the assistant message dict."""
    try:
        resp = _request(url, "/api/chat", body, timeout=timeout)
    except OllamaError as e:
        if "think" not in str(e) or "think" not in body:
            raise
        body = {k: v for k, v in body.items() if k != "think"}  # model has no thinking mode
        resp = _request(url, "/api/chat", body, timeout=timeout)
    with resp as r:
        return json.load(r)["message"]
