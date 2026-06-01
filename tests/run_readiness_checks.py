"""Safe host/container readiness checks — no uploads, no secrets printed."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

RECRUITMENT_HE = (
    "אני מחפש שוער עם לפחות 5 שנות ניסיון, רגוע תחת לחץ, "
    "טוב במשחק רגל, מוכן לעבור לצפון ושכרו עד 80,000 אירו לעונה. "
    "מי המועמד המתאים ביותר ולמה?"
)


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base}{path}", timeout=60) as resp:
        return json.loads(resp.read().decode())


def post_json(base: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def ask(base: str, question: str) -> dict:
    sid = post_json(base, "/api/sessions", {})["id"]
    return post_json(base, f"/api/sessions/{sid}/messages", {"content": question})


def main_source_name(resp: dict) -> str:
    ms = resp.get("main_source") or {}
    if isinstance(ms, dict):
        return Path(ms.get("source", "") or ms.get("display_source", "")).name
    return str(ms)


def answer_text(resp: dict) -> str:
    return (resp.get("assistant_message") or {}).get("content") or ""


def run_checks(base: str, label: str) -> dict:
    out: dict = {"label": label, "base": base}
    out["health"] = get(base, "/api/health")
    out["status"] = get(base, "/api/status")
    docs = get(base, "/api/documents")
    out["documents"] = {
        "raw_object_count": docs.get("raw_object_count"),
        "display_count": len(docs.get("documents") or []),
    }

    resp_a = ask(base, RECRUITMENT_HE)
    ans_a = answer_text(resp_a)
    out["test_a"] = {
        "refused": resp_a.get("refused"),
        "generation_mode": resp_a.get("generation_mode"),
        "main_source": main_source_name(resp_a),
        "daniel": "Daniel Cohen" in ans_a or "דניאל" in ans_a,
        "marco": "Marco Silva" in ans_a or "מרקו" in ans_a,
        "passage_markers": "【" in ans_a,
        "embedded_cv_in_names": "Position: Goalkeeper" in ans_a,
        "answer_preview": ans_a[:400],
    }

    resp_b = ask(base, "ומה השכר של Marco Silva?")
    ans_b = answer_text(resp_b)
    out["test_b"] = {
        "refused": resp_b.get("refused"),
        "main_source": main_source_name(resp_b),
        "has_78000": "78" in ans_b.replace(",", ""),
        "answer": ans_b,
    }

    resp_c = ask(base, "מי זה דונלד טראמפ?")
    out["test_c"] = {
        "refused": resp_c.get("refused"),
        "reason": resp_c.get("reason"),
        "sources_count": len(resp_c.get("sources") or []),
        "answer": answer_text(resp_c),
    }
    return out


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
    label = sys.argv[2] if len(sys.argv) > 2 else "host"
    print(json.dumps(run_checks(base, label), ensure_ascii=False, indent=2))
