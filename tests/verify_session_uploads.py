"""Verify session-scoped uploads reset on New conversation."""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from io import BytesIO
from pathlib import Path

BASE = "http://localhost:5000"
STARTERS = {
    "Avidan Risk Analysis Report.txt",
    "docker_aws.pdf",
    "Flask-lecture1.pdf",
    "Flask-lecture2.pdf",
    "for_check.txt",
}


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as resp:
        return json.loads(resp.read().decode())


def post(path: str, data: dict | None = None) -> dict:
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def upload(name: str, content: bytes) -> dict:
    boundary = "----B"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/api/documents/upload",
        body,
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def wait_ready(timeout: int = 180) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        try:
            last = get("/api/status")
            if last.get("ready") and not last.get("error"):
                return last
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(last)


def ask(session_id: str, question: str) -> dict:
    return post(f"/api/sessions/{session_id}/messages", {"content": question})


def doc_names() -> set[str]:
    return {Path(d["name"]).name for d in get("/api/documents")["documents"]}


def make_resume_pdf() -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, "Avidan Mandelman resume\nGPA: 88\n")
    out = BytesIO()
    pdf.output(out)
    return out.getvalue()


def main() -> int:
    results: dict[str, str] = {}
    fails = 0

    def record(name: str, ok: bool, detail: str = "") -> None:
        nonlocal fails
        results[name] = ("PASS" if ok else "FAIL") + (f" — {detail}" if detail else "")
        if not ok:
            fails += 1
        print(f"{name}: {results[name]}")

    wait_ready()
    record("Starter files on startup", STARTERS.issubset(doc_names()), str(sorted(doc_names())))

    sid = post("/api/sessions", {})["id"]

    r_fr = ask(sid, "מה היא בירת צרפת?")
    ans_fr = r_fr["assistant_message"]["content"]
    record(
        "for_check France (Hebrew)",
        "פריז" in ans_fr or "Paris" in ans_fr,
        ans_fr[:100],
    )

    r_ic = ask(sid, "what is the capital of Iceland?")
    ans_ic = r_ic["assistant_message"]["content"]
    record(
        "Iceland no-information",
        r_ic.get("refused") and "Paris" not in ans_ic and "Reykjavik" not in ans_ic,
        ans_ic[:100],
    )

    r_risk = ask(sid, "Who is the owner of the Risk Analysis Report?")
    ans_risk = r_risk["assistant_message"]["content"]
    record(
        "Risk Analysis Report",
        "Chief Risk Officer" in ans_risk or "CRO" in ans_risk,
        ans_risk[:100],
    )

    upload("Resume_Avidan_Mandelman.pdf", make_resume_pdf())
    wait_ready()
    record(
        "Upload Resume appears in KB",
        "Resume_Avidan_Mandelman.pdf" in doc_names(),
    )

    r_gpa = ask(sid, "what is avidan gpa?")
    ans_gpa = r_gpa["assistant_message"]["content"]
    record(
        "Resume GPA in same session",
        "88" in ans_gpa,
        ans_gpa[:100],
    )

    post("/api/session-uploads/reset", {})
    wait_ready()
    record(
        "New conversation removes Resume from KB",
        "Resume_Avidan_Mandelman.pdf" not in doc_names()
        and STARTERS.issubset(doc_names()),
        str(sorted(doc_names())),
    )

    sid3 = post("/api/sessions", {})["id"]
    r_gpa2 = ask(sid3, "what is avidan gpa?")
    ans_gpa2 = r_gpa2["assistant_message"]["content"]
    record(
        "GPA after new conversation reset",
        r_gpa2.get("refused")
        or "do not have enough information" in ans_gpa2.lower()
        or "אין לי מספיק מידע" in ans_gpa2,
        ans_gpa2[:100],
    )

    print("\n=== SUMMARY ===")
    for k, v in results.items():
        print(f"{k}: {v}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
