#!/usr/bin/env python3
"""Focused lifecycle validation (disposable sessions only)."""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "sample_scout_data" / "demo_candidates"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5001"
SKIP_PUBLIC = "--skip-public" in sys.argv
TIMEOUT = 300
POLL_INTERVAL = 3
READY_TIMEOUT = 420

BLOCKERS: list[str] = []
RESULTS: dict[str, str] = {}
SESSIONS: list[str] = []


def record(key: str, ok: bool, detail: str) -> None:
    RESULTS[key] = "PASS" if ok else f"FAIL: {detail}"
    if not ok:
        BLOCKERS.append(f"{key}: {detail}")
    print(f"{key}={'PASS' if ok else 'FAIL'} {detail[:220]}", flush=True)


def http_json(method: str, path: str, payload: dict | None = None, timeout: int = TIMEOUT) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def http_code(method: str, path: str, timeout: int = 60) -> int:
    req = urllib.request.Request(BASE + path, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.getcode()


def upload_bytes(session_id: str, filename: str, content: bytes) -> tuple[int, dict]:
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    boundary = "----scoutmatchpreflight"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {ctype}\r\n\r\n".encode(),
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{BASE}/api/sessions/{session_id}/documents/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.getcode(), json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace") or "{}"
        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            payload = {"error": body_text[:200]}
        return exc.code, payload


def upload_path(session_id: str, path: Path) -> tuple[int, dict]:
    return upload_bytes(session_id, path.name, path.read_bytes())


def new_session() -> str:
    sid = http_json("POST", "/api/sessions", {})["id"]
    SESSIONS.append(sid)
    return sid


def wait_ready(session_id: str, label: str) -> bool:
    deadline = time.time() + READY_TIMEOUT
    last: dict = {}
    while time.time() < deadline:
        last = http_json("GET", f"/api/sessions/{session_id}")
        if last.get("sync_state") == "READY" and int(last.get("document_revision") or 0) == int(
            last.get("synced_revision") or 0
        ):
            return True
        time.sleep(POLL_INTERVAL)
    record(label, False, f"sync timeout state={last.get('sync_state')}")
    return False


def ask(session_id: str, question: str, timeout: int = TIMEOUT) -> dict:
    return http_json(
        "POST",
        f"/api/sessions/{session_id}/messages",
        {"content": question},
        timeout=timeout,
    )


def answer_text(resp: dict) -> str:
    return (resp.get("assistant_message") or {}).get("content") or ""


def main_source_name(resp: dict) -> str:
    ms = resp.get("main_source") or (resp.get("assistant_message") or {}).get("main_source")
    if ms:
        return Path(ms.get("source") or ms.get("display_name") or "").name
    return ""


def source_names(resp: dict) -> list[str]:
    names: list[str] = []
    for src in resp.get("sources") or []:
        names.append(Path(src.get("source") or src.get("display_name") or "").name)
    ctx = (resp.get("assistant_message") or {}).get("context") or []
    for src in ctx:
        names.append(Path(src.get("source") or src.get("display_name") or "").name)
    return [n for n in names if n]


def refusal_ok(resp: dict) -> bool:
    return bool(resp.get("refused")) or bool((resp.get("assistant_message") or {}).get("refused"))


def list_documents(session_id: str) -> list[dict]:
    return http_json("GET", f"/api/sessions/{session_id}/documents").get("documents") or []


def doc_by_filename(session_id: str, filename: str) -> dict | None:
    target = filename.lower()
    for doc in list_documents(session_id):
        if (doc.get("display_name") or "").lower() == target:
            return doc
    return None


def delete_document(session_id: str, doc_id: int, *, async_delete: bool = False) -> dict | threading.Thread:
    if not async_delete:
        return http_json("DELETE", f"/api/sessions/{session_id}/documents/{doc_id}")

    result: dict = {}
    error: list[Exception] = []

    def worker() -> None:
        try:
            result.update(http_json("DELETE", f"/api/sessions/{session_id}/documents/{doc_id}"))
        except Exception as exc:  # noqa: BLE001
            error.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


def during_sync_ok(resp: dict, question_text: str) -> bool:
    text = answer_text(resp).lower()
    reason = resp.get("reason") or (resp.get("assistant_message") or {}).get("reason")
    stale = "45000" in text.replace(",", "") or "45,000" in answer_text(resp)
    if "eyal" not in question_text.lower():
        stale = False
    syncing = (
        reason == "documents_syncing"
        or "sync" in text
        or "updat" in text
        or "knowledge base" in text
    )
    return refusal_ok(resp) and syncing and not stale


def cleanup_session(session_id: str) -> None:
    try:
        http_json("DELETE", f"/api/sessions/{session_id}", {"delete_documents": True})
    except urllib.error.HTTPError:
        pass


def run_eyal_csv_delete() -> None:
    print("\n=== EYAL MOR CSV DELETE ===", flush=True)
    sid = new_session()
    code, _ = upload_path(sid, DEMO / "eyal_mor_cv.csv")
    record("eyal_upload", code == 201, f"http={code}")
    if code != 201 or not wait_ready(sid, "eyal_ready"):
        return

    q = "What is Eyal Mor's annual salary and is he willing to relocate?"
    before = ask(sid, q)
    before_text = answer_text(before).lower()
    src_before = source_names(before) + [main_source_name(before)]
    record(
        "eyal_before",
        "45000" in before_text.replace(",", "") or "45,000" in answer_text(before),
        answer_text(before)[:120],
    )
    record(
        "eyal_before_reloc",
        "not willing" in before_text or ("no" in before_text and "relocate" in before_text),
        before_text[:120],
    )
    record(
        "eyal_before_source",
        any("eyal_mor" in s.lower() for s in src_before),
        f"sources={src_before}",
    )

    doc = doc_by_filename(sid, "eyal_mor_cv.csv")
    if not doc or doc.get("id") is None:
        record("eyal_doc_id", False, "document missing")
        return

    thread = delete_document(sid, int(doc["id"]), async_delete=True)
    during = ask(sid, q, timeout=45)
    record("eyal_during_sync", during_sync_ok(during, q), f"reason={during.get('reason')} text={answer_text(during)[:100]}")
    if isinstance(thread, threading.Thread):
        thread.join(timeout=READY_TIMEOUT)

    if not wait_ready(sid, "eyal_after_delete_ready"):
        return

    who = ask(sid, "Who is Eyal Mor?")
    who_src = source_names(who)
    record(
        "eyal_after_who",
        refusal_ok(who) and not any("eyal_mor" in s.lower() for s in who_src),
        f"refused={refusal_ok(who)} sources={who_src}",
    )

    after = ask(sid, q)
    after_text = answer_text(after).lower()
    after_ms = main_source_name(after).lower()
    after_src = source_names(after)
    stale = "45000" in after_text.replace(",", "") or "45,000" in answer_text(after)
    bad_src = any(
        name in after_ms or any(name in s.lower() for s in after_src)
        for name in ("transfer_budget", "club_profile")
    )
    record(
        "eyal_after_salary",
        refusal_ok(after) and not stale,
        f"refused={refusal_ok(after)} main={main_source_name(after)} text={answer_text(after)[:120]}",
    )
    record(
        "eyal_after_source",
        refusal_ok(after) and not bad_src,
        f"main={main_source_name(after)} sources={after_src}",
    )

    budget = ask(sid, "What is the club's transfer budget?")
    budget_text = answer_text(budget)
    record(
        "eyal_baseline_budget",
        "100,000" in budget_text or "100000" in budget_text.replace(",", ""),
        budget_text[:120],
    )
    cleanup_session(sid)


def format_delete_lifecycle(
    ext: str,
    filename: str,
    content: bytes,
    question: str,
    *,
    expect_in_answer: str,
    salary_check: str | None = None,
) -> None:
    sid = new_session()
    code, up = upload_bytes(sid, filename, content)
    record(f"fmt_{ext}_upload", code == 201, f"http={code} err={str(up.get('error', ''))[:60]}")
    if code != 201 or not wait_ready(sid, f"fmt_{ext}_ready"):
        return

    before = ask(sid, question)
    before_src = source_names(before) + [main_source_name(before)]
    before_ok = not refusal_ok(before)
    if salary_check:
        before_ok = before_ok and salary_check.replace(",", "") in answer_text(before).replace(",", "")
    else:
        before_ok = before_ok and expect_in_answer.lower() in answer_text(before).lower()
    before_ok = before_ok and any(filename.lower() in s.lower() for s in before_src if s)
    record(f"fmt_{ext}_before", before_ok, f"text={answer_text(before)[:80]} sources={before_src}")

    doc = doc_by_filename(sid, filename)
    if not doc or doc.get("id") is None:
        record(f"fmt_{ext}_doc_id", False, f"missing id for {filename}")
        return

    thread = delete_document(sid, int(doc["id"]), async_delete=True)
    during = ask(sid, question, timeout=45)
    during_text = answer_text(during).lower()
    during_ok = refusal_ok(during) or expect_in_answer.lower() not in during_text
    if salary_check:
        during_ok = during_ok and salary_check.replace(",", "") not in during_text.replace(",", "")
    record(f"fmt_{ext}_during", during_ok, f"text={answer_text(during)[:80]}")
    if isinstance(thread, threading.Thread):
        thread.join(timeout=READY_TIMEOUT)

    if not wait_ready(sid, f"fmt_{ext}_post_del"):
        return

    after = ask(sid, question)
    after_src = source_names(after)
    record(
        f"fmt_{ext}_after",
        refusal_ok(after) and filename.lower() not in " ".join(after_src).lower(),
        f"refused={refusal_ok(after)} sources={after_src}",
    )
    cleanup_session(sid)


def run_format_regression() -> None:
    print("\n=== FORMAT DELETE LIFECYCLE ===", flush=True)
    txt = (
        "Full Name: Preflight TXT Player\n"
        "Position: Forward\n"
        "Annual Salary Expectation: 41000 EUR\n"
        "Relocation Willingness: YES\n"
    ).encode()
    format_delete_lifecycle(
        "txt",
        "preflight_txt_player.txt",
        txt,
        "Who is Preflight TXT Player?",
        expect_in_answer="Preflight TXT",
    )

    if (DEMO / "ron_ben_ari_cv.pdf").exists():
        format_delete_lifecycle(
            "pdf",
            "ron_ben_ari_cv.pdf",
            (DEMO / "ron_ben_ari_cv.pdf").read_bytes(),
            "What is Ron Ben Ari's annual salary?",
            expect_in_answer="Ron Ben Ari",
            salary_check="43000",
        )

    if (DEMO / "tal_raz_cv.docx").exists():
        format_delete_lifecycle(
            "docx",
            "tal_raz_cv.docx",
            (DEMO / "tal_raz_cv.docx").read_bytes(),
            "What is Tal Raz's annual salary?",
            expect_in_answer="Tal Raz",
            salary_check="50000",
        )

    csv_bytes = (
        "name,position,annual_salary_eur,relocation_willingness,availability,preferred_foot\n"
        "Preflight CSV Player,Forward,42000,YES,Immediate,Right\n"
    ).encode()
    format_delete_lifecycle(
        "csv",
        "preflight_csv_player.csv",
        csv_bytes,
        "Who is Preflight CSV Player?",
        expect_in_answer="Preflight CSV",
    )


def run_lifecycle() -> None:
    print("\n=== LIFECYCLE ===", flush=True)
    sid = new_session()
    upload_path(sid, DEMO / "pedro_silva_cv.txt")
    wait_ready(sid, "clear_ready")
    grounded = ask(sid, "Who is Pedro Silva?")
    record("lifecycle_clear_before", not refusal_ok(grounded), answer_text(grounded)[:80])
    http_json("POST", f"/api/sessions/{sid}/documents/clear", {})
    wait_ready(sid, "clear_sync")
    after = ask(sid, "Who is Pedro Silva?")
    record("lifecycle_clear_refuse", refusal_ok(after), f"refused={refusal_ok(after)}")
    cleared = list_documents(sid)
    record("lifecycle_clear_docs", len(cleared) == 0, f"count={len(cleared)}")
    budget = ask(sid, "What is the club's transfer budget?")
    record(
        "lifecycle_clear_budget",
        "100,000" in answer_text(budget) or "100000" in answer_text(budget).replace(",", ""),
        answer_text(budget)[:80],
    )
    msgs = http_json("GET", f"/api/sessions/{sid}").get("messages") or []
    record("lifecycle_clear_msgs", len(msgs) >= 2, f"count={len(msgs)}")
    cleanup_session(sid)

    sid2 = new_session()
    upload_path(sid2, DEMO / "ron_ben_ari_cv.pdf")
    upload_path(sid2, DEMO / "tal_raz_cv.docx")
    wait_ready(sid2, "two_ready")
    combo_q = "Can the club afford Ron Ben Ari and Tal Raz together?"
    combo = ask(sid2, combo_q)
    combo_text = answer_text(combo)
    record(
        "lifecycle_two_combo",
        "93,000" in combo_text or "93000" in combo_text.replace(",", ""),
        combo_text[:160],
    )
    record(
        "lifecycle_two_combo_remaining",
        "7,000" in combo_text or "7000" in combo_text.replace(",", ""),
        combo_text[:160],
    )
    tal = doc_by_filename(sid2, "tal_raz_cv.docx")
    if tal and tal.get("id") is not None:
        http_json("DELETE", f"/api/sessions/{sid2}/documents/{tal['id']}")
        wait_ready(sid2, "two_del_tal")
    combo2 = ask(sid2, combo_q)
    combo2_text = answer_text(combo2)
    record(
        "lifecycle_two_combo_after",
        "93,000" not in combo2_text and "93000" not in combo2_text.replace(",", ""),
        combo2_text[:160],
    )
    ron = ask(sid2, "Who is Ron Ben Ari?")
    record("lifecycle_ron_still", not refusal_ok(ron), answer_text(ron)[:80])
    tal_q = ask(sid2, "Who is Tal Raz?")
    record("lifecycle_tal_refuse", refusal_ok(tal_q), answer_text(tal_q)[:80])
    cleanup_session(sid2)

    sid_a = new_session()
    unique_name = "Isolation Unique Zed"
    unique = (
        f"Full Name: {unique_name}\n"
        "Position: Midfielder\n"
        "Annual Salary Expectation: 44000 EUR\n"
        "Relocation Willingness: YES\n"
    ).encode()
    upload_bytes(sid_a, "isolation_unique_zed.txt", unique)
    wait_ready(sid_a, "iso_a")
    a_ok = ask(sid_a, f"Who is {unique_name}?")
    record("lifecycle_iso_a", not refusal_ok(a_ok), answer_text(a_ok)[:80])
    sid_b = new_session()
    b_ok = ask(sid_b, f"Who is {unique_name}?")
    b_src = source_names(b_ok)
    record(
        "lifecycle_iso_b",
        refusal_ok(b_ok) and not any("isolation" in s.lower() for s in b_src),
        f"refused={refusal_ok(b_ok)} sources={b_src}",
    )
    cleanup_session(sid_a)
    cleanup_session(sid_b)

    sid_c = new_session()
    upload_path(sid_c, DEMO / "pedro_silva_cv.txt")
    wait_ready(sid_c, "del_conv_ready")
    try:
        del_resp = http_json("DELETE", f"/api/sessions/{sid_c}", {"delete_documents": True})
        record("lifecycle_del_conv", del_resp.get("ok", True), str(del_resp)[:120])
    except urllib.error.HTTPError as exc:
        record("lifecycle_del_conv", exc.code in (200, 404), str(exc.code))
    try:
        http_json("GET", f"/api/sessions/{sid_c}")
        record("lifecycle_del_conv_gone", False, "session still exists")
    except urllib.error.HTTPError as exc:
        record("lifecycle_del_conv_gone", exc.code == 404, str(exc.code))
    if sid_c in SESSIONS:
        SESSIONS.remove(sid_c)


def run_public_endpoints() -> None:
    print("\n=== PUBLIC ENDPOINTS ===", flush=True)
    for path, key in [
        ("/", "endpoint_home"),
        ("/api/health", "endpoint_health"),
        ("/api/status", "endpoint_status"),
        ("/static/images/home-dashboard-art.png", "endpoint_art"),
    ]:
        try:
            record(key, http_code("GET", path) == 200, path)
        except Exception as exc:  # noqa: BLE001
            record(key, False, str(exc))
    try:
        st = http_json("GET", "/api/status")
        record("status_ready", bool(st.get("ready")), str(st.get("ready")))
        record("status_baseline_ready", bool(st.get("baseline_ready")), str(st.get("baseline_ready")))
        record("status_rag_backend", st.get("rag_backend") == "aws_kb", str(st.get("rag_backend")))
        record("status_engine", st.get("engine_class") == "AWSKnowledgeBaseEngine", str(st.get("engine_class")))
        ing = (st.get("latest_ingestion") or {}).get("status")
        record("status_ingestion", ing == "COMPLETE", str(ing))
    except Exception as exc:  # noqa: BLE001
        record("status_parse", False, str(exc))


def main() -> int:
    print(f"BASE={BASE}", flush=True)
    if not SKIP_PUBLIC and "127.0.0.1" not in BASE and "localhost" not in BASE:
        run_public_endpoints()
    run_eyal_csv_delete()
    run_format_regression()
    run_lifecycle()
    print(f"\nBLOCKERS={len(BLOCKERS)}", flush=True)
    for item in BLOCKERS:
        print(f"  {item}", flush=True)
    out = ROOT / "runtime" / "final_targeted_preflight_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"blockers": BLOCKERS, "results": RESULTS}, indent=2), encoding="utf-8")
    return 1 if BLOCKERS else 0


if __name__ == "__main__":
    raise SystemExit(main())
