"""
SQLite-backed conversation memory for the course assistant.

Two tables:
- sessions(id, title, created_at, updated_at)
- messages(id, session_id, role, content, context_json, created_at)
- session_documents(id, session_id, s3_key, display_name, category, uploaded_at)
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config

from requirement_verification import _name_from_filename


DB_PATH = str(config.DB_PATH)
_local = threading.local()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        _local.conn = conn
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def init_db() -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )
        if not _column_exists(conn, "sessions", "bedrock_session_id"):
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN bedrock_session_id TEXT"
            )
        if not _column_exists(conn, "sessions", "document_revision"):
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN document_revision INTEGER NOT NULL DEFAULT 0"
            )
        if not _column_exists(conn, "sessions", "synced_revision"):
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN synced_revision INTEGER NOT NULL DEFAULT 0"
            )
        if not _column_exists(conn, "sessions", "sync_state"):
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN sync_state TEXT NOT NULL DEFAULT 'READY'"
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT NOT NULL,
                role          TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content       TEXT NOT NULL,
                context_json  TEXT,
                created_at    TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_session "
            "ON messages(session_id, id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_documents (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL,
                s3_key       TEXT NOT NULL,
                display_name TEXT NOT NULL,
                category     TEXT,
                uploaded_at  TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_documents_session "
            "ON session_documents(session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_documents_s3_key "
            "ON session_documents(s3_key)"
        )
        if not _column_exists(conn, "session_documents", "content_hash"):
            conn.execute(
                "ALTER TABLE session_documents ADD COLUMN content_hash TEXT"
            )
        for column, ddl in (
            ("parsed_player_name", "ALTER TABLE session_documents ADD COLUMN parsed_player_name TEXT"),
            ("parsed_salary_eur", "ALTER TABLE session_documents ADD COLUMN parsed_salary_eur INTEGER"),
            ("parsed_relocation", "ALTER TABLE session_documents ADD COLUMN parsed_relocation TEXT"),
            ("parsed_availability", "ALTER TABLE session_documents ADD COLUMN parsed_availability TEXT"),
            ("parsed_position", "ALTER TABLE session_documents ADD COLUMN parsed_position TEXT"),
            ("parsed_preferred_foot", "ALTER TABLE session_documents ADD COLUMN parsed_preferred_foot TEXT"),
            ("parsed_vision", "ALTER TABLE session_documents ADD COLUMN parsed_vision INTEGER"),
            ("parsed_creativity", "ALTER TABLE session_documents ADD COLUMN parsed_creativity INTEGER"),
            ("parsed_key_passing", "ALTER TABLE session_documents ADD COLUMN parsed_key_passing INTEGER"),
        ):
            if not _column_exists(conn, "session_documents", column):
                conn.execute(ddl)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_documents_content_hash "
            "ON session_documents(session_id, content_hash)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS baseline_documents (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                baseline_set_id TEXT NOT NULL,
                s3_key          TEXT NOT NULL,
                display_name    TEXT NOT NULL,
                category        TEXT,
                content_hash    TEXT,
                managed_by      TEXT NOT NULL DEFAULT 'scoutmatch',
                sync_state      TEXT NOT NULL DEFAULT 'READY',
                uploaded_at     TEXT NOT NULL,
                parsed_facts_json TEXT,
                UNIQUE(baseline_set_id, s3_key)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_baseline_documents_set "
            "ON baseline_documents(baseline_set_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS baseline_sync (
                baseline_set_id TEXT PRIMARY KEY,
                sync_state      TEXT NOT NULL DEFAULT 'READY',
                synced_at       TEXT,
                last_job_id     TEXT
            )
            """
        )


# ---------- sessions ----------

def create_session(title: str = "New conversation") -> dict:
    session_id = uuid.uuid4().hex
    now = _utcnow_iso()
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at, bedrock_session_id) "
            "VALUES (?, ?, ?, ?, NULL)",
            (session_id, title, now, now),
        )
    return {
        "id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "bedrock_session_id": None,
    }


_SESSION_SELECT = (
    "id, title, created_at, updated_at, bedrock_session_id, "
    "document_revision, synced_revision, sync_state"
)


def list_sessions() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        f"SELECT {_SESSION_SELECT} FROM sessions ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def get_session(session_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        f"SELECT {_SESSION_SELECT} FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    return dict(row) if row else None


def bump_document_revision(session_id: str) -> int:
    """Increment revision and mark session as syncing."""
    conn = get_connection()
    with conn:
        row = conn.execute(
            "SELECT document_revision FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            raise ValueError("Session not found")
        new_rev = int(row["document_revision"] or 0) + 1
        conn.execute(
            "UPDATE sessions SET document_revision = ?, sync_state = ?, updated_at = ? "
            "WHERE id = ?",
            (new_rev, config.SYNC_STATE_SYNCING, _utcnow_iso(), session_id),
        )
    return new_rev


def mark_sync_success(session_id: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE sessions SET synced_revision = document_revision, "
            "sync_state = ?, updated_at = ? WHERE id = ?",
            (config.SYNC_STATE_READY, _utcnow_iso(), session_id),
        )


def mark_sync_error(session_id: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE sessions SET sync_state = ?, updated_at = ? WHERE id = ?",
            (config.SYNC_STATE_ERROR, _utcnow_iso(), session_id),
        )


def is_retrieval_ready(session_id: str) -> bool:
    session = get_session(session_id)
    if not session:
        return False
    revision = int(session.get("document_revision") or 0)
    synced = int(session.get("synced_revision") or 0)
    state = session.get("sync_state") or config.SYNC_STATE_READY
    return state == config.SYNC_STATE_READY and revision == synced


def update_bedrock_session_id(session_id: str, bedrock_session_id: str | None) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE sessions SET bedrock_session_id = ?, updated_at = ? WHERE id = ?",
            (bedrock_session_id, _utcnow_iso(), session_id),
        )


def update_session_title(session_id: str, title: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, _utcnow_iso(), session_id),
        )


def delete_session(session_id: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM session_documents WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def clear_all_conversations() -> None:
    """Delete every session and message (Clear All / Reset Project)."""
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM sessions")


def vacuum_database_file() -> None:
    conn = get_connection()
    conn.execute("VACUUM")


# ---------- session documents ----------

def add_session_document(
    session_id: str,
    s3_key: str,
    display_name: str,
    category: str | None = None,
    *,
    content_hash: str | None = None,
    parsed_player_name: str | None = None,
    parsed_salary_eur: int | None = None,
    parsed_relocation: str | None = None,
    parsed_availability: str | None = None,
    parsed_position: str | None = None,
    parsed_preferred_foot: str | None = None,
    parsed_vision: int | None = None,
    parsed_creativity: int | None = None,
    parsed_key_passing: int | None = None,
) -> dict:
    now = _utcnow_iso()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO session_documents
                (session_id, s3_key, display_name, category, uploaded_at, content_hash,
                 parsed_player_name, parsed_salary_eur, parsed_relocation, parsed_availability,
                 parsed_position, parsed_preferred_foot, parsed_vision, parsed_creativity,
                 parsed_key_passing)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, s3_key, display_name, category, now, content_hash,
                parsed_player_name, parsed_salary_eur, parsed_relocation, parsed_availability,
                parsed_position, parsed_preferred_foot, parsed_vision, parsed_creativity,
                parsed_key_passing,
            ),
        )
    return {
        "id": cur.lastrowid,
        "session_id": session_id,
        "s3_key": s3_key,
        "display_name": display_name,
        "category": category,
        "uploaded_at": now,
        "content_hash": content_hash,
        "parsed_player_name": parsed_player_name,
        "parsed_salary_eur": parsed_salary_eur,
        "parsed_relocation": parsed_relocation,
        "parsed_availability": parsed_availability,
        "parsed_position": parsed_position,
        "parsed_preferred_foot": parsed_preferred_foot,
        "parsed_vision": parsed_vision,
        "parsed_creativity": parsed_creativity,
        "parsed_key_passing": parsed_key_passing,
    }


def _is_availability_update_document(doc: dict) -> bool:
    name = (doc.get("display_name") or "").lower()
    return "availability_update" in name or "candidate update" in name


def _is_scouting_report_document(doc: dict) -> bool:
    name = (doc.get("display_name") or "").lower()
    category = str(doc.get("category") or "").upper()
    return "scouting_report" in name or category in {"SCOUT REPORT", "SCOUTING REPORT"}


def _is_excluded_registry_document(doc: dict) -> bool:
    name = (doc.get("display_name") or "").lower()
    return any(marker in name for marker in (
        "titanic",
        "prompt_injection",
        "team_requirements",
        "tactical_requirements",
        "format_",
        "quoted_csv",
        "bom_csv",
        "duplicate_",
        "empty_file",
        "corrupt_",
        "malformed_",
        "unsupported",
        "oversized",
        "escape",
    ))


def _merge_player_fact_entry(entry: dict, doc: dict, *, enrich_only: bool = False) -> None:
    salary = doc.get("parsed_salary_eur")
    relocation = doc.get("parsed_relocation")
    position = (doc.get("parsed_position") or "").strip()
    availability = doc.get("parsed_availability")
    foot = (doc.get("parsed_preferred_foot") or "").strip()
    fname = doc.get("display_name") or ""

    if salary is not None and (not enrich_only or entry.get("annual_salary_eur") is None):
        entry["annual_salary_eur"] = int(salary)
    if relocation and (not enrich_only or not entry.get("relocation_north")):
        entry["relocation_north"] = relocation
    if position and (not enrich_only or not entry.get("position")):
        entry["position"] = position
    if availability and (not enrich_only or not entry.get("availability")):
        entry["availability"] = availability
    if foot and (not enrich_only or not entry.get("preferred_foot")):
        entry["preferred_foot"] = foot
    vision = doc.get("parsed_vision")
    creativity = doc.get("parsed_creativity")
    key_pass = doc.get("parsed_key_passing")
    if vision is not None and (not enrich_only or entry.get("vision") is None):
        entry["vision"] = int(vision)
    if creativity is not None and (not enrich_only or entry.get("creativity") is None):
        entry["creativity"] = int(creativity)
    if key_pass is not None and (not enrich_only or entry.get("key_passing") is None):
        entry["key_passing"] = int(key_pass)
    if fname and fname not in entry["source_filenames"]:
        entry["source_filenames"].append(fname)


def list_session_player_facts(session_id: str) -> list[dict]:
    """Return upload-time parsed player facts for aggregate queries."""
    docs = list_session_documents(session_id)
    merged: dict[str, dict] = {}

    def ingest(doc: dict, *, enrich_only: bool) -> None:
        if _is_excluded_registry_document(doc):
            return
        name = (doc.get("parsed_player_name") or "").strip()
        if not name:
            name = (_name_from_filename(doc.get("display_name") or "") or "").strip()
        if not name:
            return
        salary = doc.get("parsed_salary_eur")
        relocation = doc.get("parsed_relocation")
        position = (doc.get("parsed_position") or "").strip()
        foot = (doc.get("parsed_preferred_foot") or "").strip()
        availability = doc.get("parsed_availability")
        vision = doc.get("parsed_vision")
        creativity = doc.get("parsed_creativity")
        key_pass = doc.get("parsed_key_passing")
        if _is_availability_update_document(doc):
            if not name:
                return
            key = name.lower()
            entry = merged.get(key)
            if entry is None:
                entry = {"full_name": name, "source_filenames": []}
                merged[key] = entry
            if availability:
                entry["availability"] = availability
            fname = doc.get("display_name") or ""
            if fname and fname not in entry["source_filenames"]:
                entry["source_filenames"].append(fname)
            return
        if salary is None and not relocation and not position and not foot and vision is None:
            return
        key = name.lower()
        if enrich_only and key not in merged:
            return
        fname = doc.get("display_name") or ""
        entry = merged.get(key)
        if entry is None:
            entry = {
                "full_name": name,
                "relocation_north": relocation,
                "availability": availability,
                "source_filenames": [fname] if fname else [],
            }
            if salary is not None:
                entry["annual_salary_eur"] = int(salary)
            if position:
                entry["position"] = position
            if foot:
                entry["preferred_foot"] = foot
            if vision is not None:
                entry["vision"] = int(vision)
            if creativity is not None:
                entry["creativity"] = int(creativity)
            if key_pass is not None:
                entry["key_passing"] = int(key_pass)
            merged[key] = entry
            return
        _merge_player_fact_entry(entry, doc, enrich_only=enrich_only)

    for doc in reversed(docs):
        if _is_scouting_report_document(doc):
            continue
        ingest(doc, enrich_only=False)

    for doc in reversed(docs):
        if not _is_scouting_report_document(doc):
            continue
        ingest(doc, enrich_only=True)

    for doc in reversed(docs):
        if _is_availability_update_document(doc):
            ingest(doc, enrich_only=False)

    facts = list(merged.values())
    facts.sort(key=lambda row: (row.get("full_name") or "").lower())
    return facts


def find_session_document_by_content_hash(
    session_id: str,
    content_hash: str,
) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, session_id, s3_key, display_name, category, uploaded_at, content_hash
        FROM session_documents
        WHERE session_id = ? AND content_hash = ?
        ORDER BY uploaded_at DESC, id DESC
        LIMIT 1
        """,
        (session_id, content_hash),
    ).fetchone()
    return dict(row) if row else None


def find_session_document_by_display_name(
    session_id: str,
    display_name: str,
) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, session_id, s3_key, display_name, category, uploaded_at, content_hash
        FROM session_documents
        WHERE session_id = ? AND display_name = ?
        ORDER BY uploaded_at DESC, id DESC
        LIMIT 1
        """,
        (session_id, display_name),
    ).fetchone()
    return dict(row) if row else None


def list_session_documents(session_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, session_id, s3_key, display_name, category, uploaded_at, content_hash,
               parsed_player_name, parsed_salary_eur, parsed_relocation, parsed_availability,
               parsed_position, parsed_preferred_foot, parsed_vision, parsed_creativity,
               parsed_key_passing
        FROM session_documents
        WHERE session_id = ?
        ORDER BY uploaded_at DESC, id DESC
        """,
        (session_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def find_session_documents_by_display_name(display_name: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, session_id, s3_key, display_name, category, uploaded_at
        FROM session_documents
        WHERE display_name = ?
        ORDER BY uploaded_at DESC, id DESC
        """,
        (display_name,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_session_document(session_id: str, document_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, session_id, s3_key, display_name, category, uploaded_at
        FROM session_documents
        WHERE session_id = ? AND id = ?
        """,
        (session_id, document_id),
    ).fetchone()
    return dict(row) if row else None


def delete_session_document(session_id: str, document_id: int) -> dict | None:
    doc = get_session_document(session_id, document_id)
    if not doc:
        return None
    conn = get_connection()
    with conn:
        conn.execute(
            "DELETE FROM session_documents WHERE session_id = ? AND id = ?",
            (session_id, document_id),
        )
    return doc


def clear_session_documents(session_id: str) -> list[dict]:
    docs = list_session_documents(session_id)
    conn = get_connection()
    with conn:
        conn.execute(
            "DELETE FROM session_documents WHERE session_id = ?",
            (session_id,),
        )
    return docs


# ---------- messages ----------

def add_message(
    session_id: str,
    role: str,
    content: str,
    context: list | None = None,
    *,
    refused: bool | None = None,
    reason: str | None = None,
    generation_mode: str | None = None,
    main_source: dict | None = None,
    document_revision_at_answer: int | None = None,
) -> dict:
    if role not in ("user", "assistant"):
        raise ValueError(f"Invalid role: {role}")

    now = _utcnow_iso()
    meta = {
        "context": context,
        "refused": refused,
        "reason": reason,
        "generation_mode": generation_mode,
        "main_source": main_source,
        "document_revision_at_answer": document_revision_at_answer,
    }
    context_json = json.dumps(meta) if any(v is not None for v in meta.values()) else None

    conn = get_connection()
    with conn:
        cur = conn.execute(
            "INSERT INTO messages (session_id, role, content, context_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, context_json, now),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )

    return {
        "id": cur.lastrowid,
        "session_id": session_id,
        "role": role,
        "content": content,
        "context": context,
        "refused": refused,
        "reason": reason,
        "generation_mode": generation_mode,
        "main_source": main_source,
        "document_revision_at_answer": document_revision_at_answer,
        "created_at": now,
    }


def get_messages(session_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, session_id, role, content, context_json, created_at "
        "FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()

    messages = []
    for row in rows:
        item = dict(row)
        ctx_raw = item.pop("context_json", None)
        if ctx_raw:
            try:
                parsed = json.loads(ctx_raw)
            except json.JSONDecodeError:
                parsed = ctx_raw
            if isinstance(parsed, dict) and "context" in parsed:
                item["context"] = parsed.get("context")
                item["refused"] = parsed.get("refused")
                item["reason"] = parsed.get("reason")
                item["generation_mode"] = parsed.get("generation_mode")
                item["main_source"] = parsed.get("main_source")
                item["document_revision_at_answer"] = parsed.get(
                    "document_revision_at_answer"
                )
            elif isinstance(parsed, list):
                item["context"] = parsed
            else:
                item["context"] = None
        else:
            item["context"] = None
        messages.append(item)
    return messages


def get_history_for_llm(session_id: str, limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM messages "
        "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ---------- baseline club knowledge ----------


def upsert_baseline_document(
    baseline_set_id: str,
    s3_key: str,
    display_name: str,
    *,
    category: str | None = None,
    content_hash: str | None = None,
    managed_by: str = "scoutmatch",
    sync_state: str = config.BASELINE_SYNC_STATE_READY,
    parsed_facts: dict | None = None,
) -> dict:
    now = _utcnow_iso()
    facts_json = json.dumps(parsed_facts) if parsed_facts else None
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO baseline_documents (
                baseline_set_id, s3_key, display_name, category, content_hash,
                managed_by, sync_state, uploaded_at, parsed_facts_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(baseline_set_id, s3_key) DO UPDATE SET
                display_name = excluded.display_name,
                category = excluded.category,
                content_hash = excluded.content_hash,
                managed_by = excluded.managed_by,
                sync_state = excluded.sync_state,
                uploaded_at = excluded.uploaded_at,
                parsed_facts_json = excluded.parsed_facts_json
            """,
            (
                baseline_set_id,
                s3_key,
                display_name,
                category,
                content_hash,
                managed_by,
                sync_state,
                now,
                facts_json,
            ),
        )
    row = conn.execute(
        "SELECT * FROM baseline_documents WHERE baseline_set_id = ? AND s3_key = ?",
        (baseline_set_id, s3_key),
    ).fetchone()
    return dict(row) if row else {}


def list_baseline_documents(baseline_set_id: str | None = None) -> list[dict]:
    set_id = baseline_set_id or config.AWS_BASELINE_SET_ID
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM baseline_documents WHERE baseline_set_id = ? ORDER BY display_name",
        (set_id,),
    ).fetchall()
    results: list[dict] = []
    for row in rows:
        item = dict(row)
        raw = item.pop("parsed_facts_json", None)
        if raw:
            try:
                item["parsed_facts"] = json.loads(raw)
            except json.JSONDecodeError:
                item["parsed_facts"] = {}
        else:
            item["parsed_facts"] = {}
        results.append(item)
    return results


def get_baseline_document(baseline_set_id: str, s3_key: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM baseline_documents WHERE baseline_set_id = ? AND s3_key = ?",
        (baseline_set_id, s3_key),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    raw = item.pop("parsed_facts_json", None)
    item["parsed_facts"] = json.loads(raw) if raw else {}
    return item


def delete_baseline_document_row(baseline_set_id: str, s3_key: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "DELETE FROM baseline_documents WHERE baseline_set_id = ? AND s3_key = ?",
            (baseline_set_id, s3_key),
        )


def list_baseline_managed_keys(baseline_set_id: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT s3_key FROM baseline_documents WHERE baseline_set_id = ?",
        (baseline_set_id,),
    ).fetchall()
    return [r["s3_key"] for r in rows]


def get_baseline_sync_state(baseline_set_id: str | None = None) -> dict:
    set_id = baseline_set_id or config.AWS_BASELINE_SET_ID
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM baseline_sync WHERE baseline_set_id = ?",
        (set_id,),
    ).fetchone()
    if row:
        return dict(row)
    return {
        "baseline_set_id": set_id,
        "sync_state": config.BASELINE_SYNC_STATE_READY,
        "synced_at": None,
        "last_job_id": None,
    }


def set_baseline_sync_state(
    baseline_set_id: str,
    *,
    sync_state: str,
    last_job_id: str | None = None,
) -> None:
    now = _utcnow_iso()
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO baseline_sync (baseline_set_id, sync_state, synced_at, last_job_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(baseline_set_id) DO UPDATE SET
                sync_state = excluded.sync_state,
                synced_at = excluded.synced_at,
                last_job_id = excluded.last_job_id
            """,
            (
                baseline_set_id,
                sync_state,
                now if sync_state == config.BASELINE_SYNC_STATE_READY else None,
                last_job_id,
            ),
        )


def is_baseline_retrieval_ready(baseline_set_id: str | None = None) -> bool:
    if not config.BASELINE_KNOWLEDGE_ENABLED:
        return True
    state = get_baseline_sync_state(baseline_set_id).get("sync_state")
    return state == config.BASELINE_SYNC_STATE_READY


def aggregate_baseline_club_facts(baseline_set_id: str | None = None) -> dict:
    """Merge parsed facts from all baseline documents for deterministic answers."""
    merged: dict = {}
    for doc in list_baseline_documents(baseline_set_id):
        facts = doc.get("parsed_facts") or {}
        for key, value in facts.items():
            if value is None:
                continue
            if key == "urgent_positions" and isinstance(value, list):
                existing = merged.setdefault("urgent_positions", [])
                for pos in value:
                    if pos not in existing:
                        existing.append(pos)
            elif key not in merged or merged[key] in (None, "", []):
                merged[key] = value
    return merged
