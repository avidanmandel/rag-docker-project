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
        ):
            if not _column_exists(conn, "session_documents", column):
                conn.execute(ddl)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_documents_content_hash "
            "ON session_documents(session_id, content_hash)"
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
) -> dict:
    now = _utcnow_iso()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO session_documents
                (session_id, s3_key, display_name, category, uploaded_at, content_hash,
                 parsed_player_name, parsed_salary_eur, parsed_relocation, parsed_availability)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, s3_key, display_name, category, now, content_hash,
                parsed_player_name, parsed_salary_eur, parsed_relocation, parsed_availability,
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
    }


def list_session_player_facts(session_id: str) -> list[dict]:
    """Return upload-time parsed player facts for aggregate queries."""
    docs = list_session_documents(session_id)
    facts: list[dict] = []
    seen: set[str] = set()
    for doc in docs:
        name = (doc.get("parsed_player_name") or "").strip()
        salary = doc.get("parsed_salary_eur")
        if not name or salary is None:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        facts.append({
            "full_name": name,
            "annual_salary_eur": int(salary),
            "relocation_north": doc.get("parsed_relocation"),
            "availability": doc.get("parsed_availability"),
            "source_filenames": [doc.get("display_name") or ""],
        })
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
               parsed_player_name, parsed_salary_eur, parsed_relocation, parsed_availability
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
