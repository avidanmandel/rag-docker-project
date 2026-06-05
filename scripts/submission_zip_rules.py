"""Shared submission ZIP inclusion and forbidden-path rules."""

from __future__ import annotations

import re
from pathlib import Path

ALLOWED_ENV_EXAMPLES = {".env.example", ".env.ec2.example"}

EXCLUDE_DIR_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".aws",
    "artifacts",
    "runtime",
    "dist",
    ".pytest_cache",
    "screenshoot",
    ".local",
    ".cursor",
    "node_modules",
}

EXCLUDE_FILE_GLOBS = ("*.pem", "*.key", "*.log", "chat.db", "*.db", "*.bak", "*.sqlite", "*.sqlite3")

EXCLUDE_FILE_NAMES = {
    "fix_agent_model.py",
    "repair_agent_runtime.py",
    "secret_scan_report.json",
}

EXCLUDE_PATH_RE = re.compile(
    r"(^|/)(home-preview-|submission_evidence/archive|docs/archive|tests/escape\.txt|"
    r"static/images/(design-reference|home-dashboard-panel|player-home|sir-alex-home)\.png|"
    r"scripts/(audit_|deploy_session_docs_v[3-7]|validate_candidate|validate_prod|validate_public|"
    r"candidate_|cutover_session_docs_v[34])|rollback/)"
)

FORBIDDEN_IN_ZIP_RE = re.compile(
    r"(?:^|/)"
    r"(?:"
    r"\.local(?:/|$)|"
    r"\.env(?:\.agent)?(?:/|$)|"
    r"\.git(?:/|$)|"
    r"__pycache__(?:/|$)|"
    r"\.pytest_cache(?:/|$)|"
    r"artifacts(?:/|$)|"
    r"(?:^|/)chat\.db$|"
    r"\.pem$|"
    r"\.key$|"
    r"fix_agent_model\.py$|"
    r"repair_agent_runtime\.py$|"
    r"secret_scan_report\.json$"
    r")",
    re.IGNORECASE,
)


def should_include(path: Path, *, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    if rel.startswith("dist/"):
        return False
    parts = rel.split("/")
    if any(p in EXCLUDE_DIR_PARTS for p in parts):
        return False
    if path.name in EXCLUDE_FILE_NAMES:
        return False
    if path.name.startswith(".env"):
        return path.name in ALLOWED_ENV_EXAMPLES
    for pat in EXCLUDE_FILE_GLOBS:
        if path.match(pat):
            return False
    if EXCLUDE_PATH_RE.search(rel):
        return False
    return True


def find_forbidden_zip_entries(entries: list[str]) -> list[str]:
    forbidden: list[str] = []
    for entry in entries:
        normalized = entry.replace("\\", "/")
        base = normalized.rsplit("/", 1)[-1]
        if base in ALLOWED_ENV_EXAMPLES:
            continue
        if base == ".env" or base == ".env.agent":
            forbidden.append(normalized)
            continue
        if normalized.endswith(".pem") or normalized.endswith(".key"):
            forbidden.append(normalized)
            continue
        if FORBIDDEN_IN_ZIP_RE.search(normalized):
            forbidden.append(normalized)
    return sorted(set(forbidden))
