"""Full final verification against a running Docker/local instance."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

BASE = "http://localhost:5000"
TIMEOUT = 120


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as resp:
        return json.loads(resp.read().decode())


def _post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def _upload(name: str, content: bytes, mime: str = "application/octet-stream") -> dict:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/api/documents/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def wait_ready(timeout: int = TIMEOUT) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        try:
            last = _get("/api/status")
            if last.get("ready") and not last.get("error"):
                return last
        except Exception:
            pass
        time.sleep(3)
    raise TimeoutError(f"Engine not ready after {timeout}s: {last}")


def ask(question: str, session_id: str | None = None) -> dict:
    if not session_id:
        session_id = _post_json("/api/sessions", {})["id"]
    return _post_json(f"/api/sessions/{session_id}/messages", {"content": question})


def main_source(resp: dict) -> str:
    ctx = resp.get("assistant_message", {}).get("context") or []
    if not ctx:
        return ""
    best = max(ctx, key=lambda c: c.get("score", -1))
    page = best.get("page")
    src = Path(best.get("source", "")).name
    return f"{src} p.{page}" if page else src


def make_test_pdf() -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(
        0,
        8,
        "Project codename: Blue Falcon\n"
        "Secret verification code: RAG-777\n"
        "This document is used to test PDF upload.",
    )
    out = BytesIO()
    pdf.output(out)
    return out.getvalue()


def test_empty_kb_local() -> bool:
    from rag_engine import RAGEngine

    engine = RAGEngine()
    engine.ready = True
    engine.chunks = []
    engine.index = None
    en = engine.answer("What is Flask?")
    he = engine.answer("מה זה Flask?")
    return (
        en["answer"] == "I do not have a knowledge base available to answer this question."
        and he["answer"] == "אין לי בסיס נתונים זמין כדי לענות על השאלה הזאת."
        and en["context"] == []
        and en["refused"]
    )


def run() -> int:
    report: dict[str, str] = {}
    fails = 0

    def record(name: str, ok: bool, detail: str = "") -> None:
        nonlocal fails
        report[name] = ("PASS" if ok else "FAIL") + (f" — {detail}" if detail else "")
        if not ok:
            fails += 1
        print(f"{name}: {report[name]}".encode("ascii", "backslashreplace").decode())

    # Empty KB (local engine, no API keys needed for this path)
    try:
        record("Empty/no knowledge base case", test_empty_kb_local())
    except Exception as exc:
        record("Empty/no knowledge base case", False, str(exc))

    try:
        health = _get("/api/health")
        record("/api/health", health.get("ok") is True and health.get("flask") == "running")
    except Exception as exc:
        record("/api/health", False, str(exc))

    try:
        status = wait_ready()
        sources = {Path(s).name for s in status.get("sources", [])}
        needed = {
            "Avidan Risk Analysis Report.txt",
            "docker_aws.pdf",
            "Flask-lecture1.pdf",
            "Flask-lecture2.pdf",
            "for_check.txt",
        }
        ok = (
            status.get("ready") is True
            and status.get("chunks", 0) > 0
            and needed.issubset(sources)
        )
        record(
            "/api/status",
            ok,
            f"chunks={status.get('chunks')} sources={sorted(sources)}",
        )
        record("Initial knowledge base indexed", ok)
        record(
            "Avidan Risk Analysis Report.txt indexed",
            "Avidan Risk Analysis Report.txt" in sources,
        )
    except Exception as exc:
        record("/api/status", False, str(exc))
        record("Initial knowledge base indexed", False, str(exc))
        record("Avidan Risk Analysis Report.txt indexed", False, str(exc))
        print(json.dumps(report, indent=2))
        return 1

    risk_tests = [
        ("Risk A", "What is the purpose of the Risk Analysis Report?", ["identifies", "evaluates", "confidentiality"]),
        ("Risk B", "Who is the owner of the report?", ["Chief Risk Officer", "CRO"]),
        ("Risk C", "What are the risks R-01 to R-05?", ["R-01", "R-02", "malware", "VPN", "SCADA"]),
        ("Risk D", "What is the treatment strategy for R-02?", ["VPN", "MFA", "24"]),
        ("Risk E", "What is the deadline for R-05?", ["31 Dec 2025", "2025"]),
        ("Risk F", "איזה סיכון קשור ל-VPN?", ["R-02", "VPN"]),
    ]
    risk_ok = True
    sid = _post_json("/api/sessions", {})["id"]
    for label, q, keys in risk_tests:
        try:
            resp = ask(q, sid)
            ans = resp["assistant_message"]["content"]
            ok = not resp.get("refused") and any(k.lower() in ans.lower() for k in keys)
            if not ok:
                risk_ok = False
                print(f"  {label} FAIL: {ans[:160]}")
        except Exception as exc:
            risk_ok = False
            print(f"  {label} FAIL: {exc}")
    record("Strict RAG behavior works", risk_ok, "Risk Analysis Report questions")

    try:
        sid = _post_json("/api/sessions", {})["id"]
        resp = ask("What is the capital of France?", sid)
        ans = resp["assistant_message"]["content"]
        ctx = resp["assistant_message"].get("context") or []
        ok = (
            resp.get("refused")
            and "Paris" not in ans
            and "do not have enough information" in ans
            and len(ctx) == 0
        )
        record("Out-of-scope question does not use general knowledge", ok, ans[:120])
    except Exception as exc:
        record("Out-of-scope question does not use general knowledge", False, str(exc))

    # TXT upload
    try:
        txt = (
            "קוראים לי רועי בן אביתר\n"
            "832 אני בן\n"
            "אני אוהב לאכול במבה\n"
            "לא אוהב לשתות נוטלה עם קפה\n"
        ).encode("utf-8")
        _upload("for_check.txt", txt, "text/plain")
        wait_ready()
        resp = ask("answer me from for_check.txt בן כמה רועי?")
        ans = resp["assistant_message"]["content"]
        src = main_source(resp)
        ok = "832" in ans and "for_check.txt" in src
        record("TXT upload works", ok, f"answer={ans[:80]} source={src}")
    except Exception as exc:
        record("TXT upload works", False, str(exc))

    # PDF upload
    try:
        pdf_bytes = make_test_pdf()
        _upload("upload_test_knowledge_base.pdf", pdf_bytes, "application/pdf")
        wait_ready()
        r1 = ask("What is the project codename?")
        r2 = ask("What is the secret verification code?")
        a1 = r1["assistant_message"]["content"]
        a2 = r2["assistant_message"]["content"]
        s1 = main_source(r1)
        ok = (
            "Blue Falcon" in a1
            and "upload_test_knowledge_base.pdf" in s1
            and "RAG-777" in a2
        )
        record("PDF upload works", ok, f"codename={a1[:60]} code={a2[:40]} source={s1}")
    except Exception as exc:
        record("PDF upload works", False, str(exc))

    # Clear All keeps starter files
    try:
        _post_json("/api/reset-all", {"confirm": True})
        wait_ready()
        docs = _get("/api/documents")["documents"]
        names = {Path(d["name"]).name for d in docs}
        needed = {
            "Avidan Risk Analysis Report.txt",
            "docker_aws.pdf",
            "Flask-lecture1.pdf",
            "Flask-lecture2.pdf",
            "for_check.txt",
        }
        ok = set(names) == needed and "upload_test_knowledge_base.pdf" not in names
        record("Clear All keeps starter files", ok, f"remaining={sorted(names)}")
    except Exception as exc:
        record("Clear All keeps starter files", False, str(exc))

    print("\n=== FINAL REPORT ===")
    for k, v in report.items():
        print(f"{k}: {v}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
