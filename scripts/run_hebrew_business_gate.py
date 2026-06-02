#!/usr/bin/env python3
"""Focused Hebrew business-intent gate (v13) — disposable sessions only."""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "sample_scout_data" / "demo_candidates"

STRICT = "--strict" in sys.argv
_args = [a for a in sys.argv[1:] if a != "--strict"]
BASE = _args[0] if _args else "http://127.0.0.1:5001"
TIMEOUT = 180
BLOCKERS: list[str] = []
SESSIONS: list[str] = []

DEMO_UPLOADS = [
    "ron_ben_ari_cv.pdf",
    "dor_levi_cv.docx",
    "tal_raz_cv.docx",
    "eyal_mor_cv.csv",
    "pedro_silva_cv.txt",
]

HE_BASELINE_URGENT = [
    "אילו עמדות דורשות חיזוק דחוף?",
    "איזה עמדות צריך לחזק בדחיפות?",
    "באילו עמדות הקבוצה צריכה חיזוק?",
    "מהן העמדות הדחופות לחיזוק?",
]
HE_BASELINE_AVAIL = [
    "למה זמינות מיידית חשובה?",
    "מדוע זמינות מיידית חשובה?",
    "למה חשוב שהשחקן יהיה זמין מיד?",
    "למה צריך שחקן שיכול להצטרף מיד?",
]
HE_CHEAPEST_RB = [
    "מי המגן הימני הזול ביותר?",
    "מי המגן הימני הכי זול?",
    "איזה מגן ימני הוא הזול ביותר?",
    "מהו המגן הימני הזול ביותר?",
]
HE_BUDGET_COMBO = [
    "האם המועדון יכול להרשות לעצמו גם את רון בן ארי וגם את טל רז?",
    "האם הקבוצה יכולה להרשות לעצמה להחתים את רון בן ארי ואת טל רז?",
    "האם התקציב מספיק לרון בן ארי ולטל רז?",
    "האם אפשר להחתים יחד את רון בן ארי ואת טל רז?",
    "האם אפשר לצרף את רון בן ארי ואת טל רז במסגרת התקציב?",
]
HE_CENTER_BACK = "מי הבלם הימני הזול ביותר?"


def record(tid: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"HE-{tid} {status} {detail}", flush=True)
    if not ok:
        BLOCKERS.append(f"{tid}: {detail}")


def http_json(method: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def ask(session_id: str, question: str) -> dict:
    return http_json("POST", f"/api/sessions/{session_id}/messages", {"content": question})


def answer_text(resp: dict) -> str:
    return (resp.get("assistant_message") or {}).get("content") or ""


def new_session() -> str:
    sid = http_json("POST", "/api/sessions")["id"]
    SESSIONS.append(sid)
    return sid


def upload_demo(session_id: str, name: str) -> None:
    path = DEMO_DIR / name
    data = path.read_bytes()
    boundary = "----hegate"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n\r\n'.encode(),
        data,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{BASE}/api/sessions/{session_id}/documents/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=TIMEOUT)


def wait_ready(session_id: str) -> None:
    for _ in range(48):
        s = http_json("GET", f"/api/sessions/{session_id}")
        if s.get("sync_state") == "READY" and int(s.get("document_revision") or 0) == int(s.get("synced_revision") or 0):
            return
        time.sleep(5)
    raise RuntimeError(f"sync timeout {session_id}")


def delete_session(session_id: str) -> None:
    data = json.dumps({"delete_documents": True}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/sessions/{session_id}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )
    urllib.request.urlopen(req, timeout=TIMEOUT)


def main() -> int:
    for i, q in enumerate(HE_BASELINE_URGENT):
        sid = new_session()
        resp = ask(sid, q)
        text = answer_text(resp)
        ok = not resp.get("refused") and all(x in text for x in ("מגן ימני", "קשר התקפי", "חלוץ"))
        record(f"BASE-URGENT-{i}", ok, text[:120])
        delete_session(sid)

    for i, q in enumerate(HE_BASELINE_AVAIL):
        sid = new_session()
        resp = ask(sid, q)
        text = answer_text(resp)
        ok = not resp.get("refused") and "5" in text and "18" in text
        record(f"BASE-AVAIL-{i}", ok, text[:120])
        delete_session(sid)

    sid = new_session()
    for f in DEMO_UPLOADS:
        upload_demo(sid, f)
    wait_ready(sid)

    for i, q in enumerate(HE_CHEAPEST_RB):
        resp = ask(sid, q)
        text = answer_text(resp).replace(",", "")
        ok = not resp.get("refused") and "ron ben ari" in text.lower() and re.search(r"43[\s,]*000", text.lower())
        record(f"LIVE-RB-{i}", ok, text[:120])

    for i, q in enumerate(HE_BUDGET_COMBO):
        resp = ask(sid, q)
        text = answer_text(resp).replace(",", "")
        ok = not resp.get("refused") and ("כן" in text or "yes" in text.lower()) and "93" in text
        record(f"LIVE-BUDGET-{i}", ok, text[:120])

    cb = ask(sid, HE_CENTER_BACK)
    cb_text = answer_text(cb)
    record(
        "LIVE-CB-DISTINCT",
        not cb.get("refused") and "בלם ימני" in cb_text and "43,000" not in cb_text,
        cb_text[:120],
    )

    en = ask(sid, "Who is the cheapest right back?")
    record("EN-RB", "ron ben ari" in answer_text(en).lower(), answer_text(en)[:80])

    delete_session(sid)

    print(f"BLOCKERS {len(BLOCKERS)}", flush=True)
    for b in BLOCKERS:
        print(f"BLOCKER {b}", flush=True)
    for sid in SESSIONS:
        print(f"DISPOSABLE_SESSION {sid}", flush=True)
    return 1 if BLOCKERS else 0


if __name__ == "__main__":
    raise SystemExit(main())
