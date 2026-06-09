#!/usr/bin/env python3
"""Quick HTTP probe of V2 staging flows via /api/sessions (run on EC2 or through tunnel)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.getenv("SCOUTMATCH_V2_STAGING_URL", "http://127.0.0.1:5002").rstrip("/")
TIMEOUT = int(os.getenv("SCOUTMATCH_PROBE_TIMEOUT", "320"))


def req(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    request = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def chat(session_id: str, content: str) -> dict:
    return req("POST", f"/api/sessions/{session_id}/messages", {"content": content})


def probe(label: str, prompt: str) -> dict:
    sess = req("POST", "/api/sessions", {})
    sid = sess["id"]
    t0 = time.time()
    try:
        out = chat(sid, prompt)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"label": label, "error": f"HTTP {exc.code}: {body[:300]}", "elapsed_s": round(time.time() - t0, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"label": label, "error": str(exc), "elapsed_s": round(time.time() - t0, 1)}
    meta = out.get("agent_metadata") or {}
    pending = meta.get("pending_return_control") or {}
    ans = (out.get("assistant_message") or {}).get("content") or ""
    return {
        "label": label,
        "elapsed_s": round(time.time() - t0, 1),
        "pending": bool(pending.get("invocation_id")),
        "function": pending.get("function"),
        "confirmation_card": bool(meta.get("confirmation_card")),
        "lineup_route": bool(meta.get("lineup_image_route")),
        "answer_snippet": ans[:240].replace("\n", " "),
    }


def main() -> int:
    probes = [
        ("no_lineup", "Show me the updated proposed lineup and squad-risk board."),
        ("transfer", "Open a transfer-out review case for Daniel Cohen."),
        ("mission", "Create a scouting mission for Ron Ben Ari's next match and add it to my calendar."),
        ("critical", "I choose Ron Ben Ari as our right-back candidate. Submit the recommendation for management review."),
        ("lineup_save", "Save and show the proposed 4-3-3 lineup for head-coach review."),
    ]
    report = [probe(label, prompt) for label, prompt in probes]
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
