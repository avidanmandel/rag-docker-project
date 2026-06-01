"""
Amazon Bedrock Knowledge Base backend for ScoutMatch AI.

Production path: retrieve() → ScoutMatch filter → diverse context → Bedrock Converse.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Any

import boto3

import config
from requirement_verification import (
    EXACT_MATCH_ACKNOWLEDGMENT_RETRY_INSTRUCTION,
    MATRIX_CONTRADICTION_RETRY_INSTRUCTION,
    PLAYER_NAME_VARIANTS,
    build_safe_exact_match_fallback,
    build_verified_candidate_matrix,
    extract_recruitment_requirements,
    extract_verified_player_facts,
    format_verified_matrix_for_prompt,
    should_build_verified_matrix,
    validate_answer_against_verified_matrix,
    validate_exact_match_acknowledgment,
)

# Test and internal aliases
_extract_verified_player_facts = extract_verified_player_facts
_extract_recruitment_requirements = extract_recruitment_requirements
_build_verified_candidate_matrix = build_verified_candidate_matrix
_validate_answer_against_verified_matrix = validate_answer_against_verified_matrix

logger = logging.getLogger(__name__)

AWS_KB_MODE_MSG = (
    "ScoutMatch AWS mode manages player documents in Amazon S3. "
    "Use Upload CV / Document in the sidebar."
)

_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")
_PASSAGE_MARKER_FULL_RE = re.compile(r"Passage\s*%\[\d+\]%", re.IGNORECASE)
_PASSAGE_MARKER_SHORT_RE = re.compile(r"(?<![\d%])%\[\d+\]%(?![\d%])")
_INTERNAL_MARKER_RE = re.compile(
    r"Passage\s*%\[\d+\]%"
    r"|(?<![\d%])%\[\d+\]%(?![\d%])"
    r"|\bthe one highlighted\b"
    r"|\bhighlighted in\b"
    r"|\bPassage\s+\d+\b",
    re.IGNORECASE,
)
_FULL_NAME_RE = re.compile(r"Full Name:\s*(.+?)(?:\n|$)", re.IGNORECASE)
_POSITION_PREFIXES = (
    "goalkeeper_",
    "defender_",
    "midfielder_",
    "forward_",
)

EXPLICIT_GENERATION_PROMPT = """You are ScoutMatch AI, an AI-powered football recruitment assistant.

Answer only from the provided retrieved ScoutMatch context.
Do not use general knowledge.
Do not invent player facts, salaries, years of experience, clubs, skills, relocation preferences, or achievements.

Answer in the same language as the user's question.

When comparing or recommending players:
- Copy numeric facts exactly from the context. Never invent missing values.
- Compare every candidate that appears in the context.
- Check each mandatory requirement one by one for each candidate.
- Never claim that 4 years satisfies a minimum of 5 years.
- Never claim that 90,000 EUR satisfies a maximum budget of 80,000 EUR.
- Never claim that relocation unwilling satisfies relocation required.
- If a value is missing from the context, say the information is missing.
- If no player satisfies all requirements, state clearly in Hebrew when answering in Hebrew:
  "לא נמצא מועמד שעומד בכל דרישות החובה."
- You may identify the closest partial match, but list every unmet requirement.
- Before writing the final answer, mentally build a compact requirements matrix internally.
  Do not expose chain-of-thought or internal analysis. Return only the final user-facing answer.
- State the full player name explicitly when recommending or comparing.
  Use the English full name exactly as written in the source documents (for example Daniel Cohen).
- Explain that the result is an AI-assisted assessment based on uploaded documents only.

Never expose internal passage labels or retrieval placeholders.

If the provided context does not answer the question, return the strict refusal message only."""

_NAME_RETRY_INSTRUCTION = (
    "Your previous draft did not name a player explicitly.\n"
    "Rewrite the answer using only the provided ScoutMatch context.\n"
    "State the full player name explicitly using the English name from the documents "
    "(for example Daniel Cohen).\n"
    "If the context does not support a named recommendation, return the strict refusal message."
)

_PLAYER_NAME_VARIANTS = PLAYER_NAME_VARIANTS

_HEBREW_PLAYER_NAME_OVERRIDES: dict[str, str] = {
    "אור דוד": "Or David",
    "לוקה רומאנו": "Luca Romano",
    "עמית לוי": "Amit Levy",
}


def _build_hebrew_to_english_player_names() -> dict[str, str]:
    mapping = dict(_HEBREW_PLAYER_NAME_OVERRIDES)
    for english, variants in _PLAYER_NAME_VARIANTS.items():
        english_title = " ".join(part.capitalize() for part in english.split())
        for variant in variants:
            mapping[variant] = english_title
    return mapping


_HEBREW_TO_ENGLISH_PLAYER_NAMES = _build_hebrew_to_english_player_names()

_PROFILE_NAME_BLOCKLIST = frozenset({
    "player",
    "candidate",
    "unknown player",
    "שחקן",
    "מועמד",
    "שחקן שלא קיים",
    "שחקן לא קיים",
})

_PLAYER_NAME_CAPTURE = (
    r"[A-Za-z\u0590-\u05FF][\w\u0590-\u05FF\-']*"
    r"(?:\s+[A-Za-z\u0590-\u05FF][\w\u0590-\u05FF\-']*){0,3}"
)

_OUT_OF_DOMAIN_ENTITIES = (
    "donald trump",
    "דונלד טראמפ",
    "trump",
    "capital of new zealand",
    "בירת ניו זילנד",
    "what is the capital",
    "מהי בירת",
)

_SCOUTMATCH_DOMAIN_KEYWORDS = (
    "goalkeeper",
    "goal keeper",
    "player",
    "football",
    "soccer",
    "scout",
    "recruit",
    "salary",
    "relocation",
    "transfer",
    "squad",
    "position",
    "striker",
    "defender",
    "midfielder",
    "winger",
    "build-up",
    "build up",
    "cv",
    "report",
    "availability",
    "contract",
    "שוער",
    "שחקן",
    "שכר",
    "גיוס",
    "מועמד",
    "קבוצה",
    "דרישות",
    "ניסיון",
    "העברה",
    "מיקום",
    "חוזה",
    "רגל",
    "התאים",
    "מוכן לעבור",
    "scouting",
    "requirements",
)

_FOLLOW_UP_PATTERNS = (
    r"\bwhat salary\b",
    r"\bhow much\b",
    r"\bhow many years\b",
    r"\bwilling to relocate\b",
    r"\bwhat about his\b",
    r"\bdoes he expect\b",
    r"ומה השכר",
    r"כמה שכר",
    r"כמה שנות",
    r"האם הוא מוכן",
    r"שכר שלו",
    r"שנות ניסיון יש לו",
    r"האם הוא מוכן לעבור",
)

_FOOTBALL_HISTORY_MARKERS = (
    "goalkeeper",
    "player",
    "שוער",
    "שחקן",
    "cohen",
    "levi",
    "azulay",
    "silva",
    "marco",
    "daniel",
    "yossi",
    "omer",
    "מועמד",
    "build-up",
    "recruitment",
    "גיוס",
    "משחק רגל",
    "football",
)


def _contains_hebrew(text: str) -> bool:
    return bool(_HEBREW_RE.search(text or ""))


def _refusal_text(question: str) -> str:
    if _HEBREW_RE.search(question):
        return config.REFUSAL_TEXT_HE
    return config.REFUSAL_TEXT_EN


def _looks_like_refusal(answer: str) -> bool:
    lowered = (answer or "").strip().lower()
    if not lowered:
        return True
    markers = (
        "do not have enough information",
        "don't have enough information",
        "not enough information",
        "cannot answer",
        "can't answer",
        "אין לי מספיק מידע",
    )
    return any(m in lowered for m in markers)


def _language_instruction_for_question(question: str) -> str:
    if _HEBREW_RE.search(question):
        return (
            "Language requirement: The user's question is in Hebrew. "
            "Write your entire answer in Hebrew."
        )
    return (
        "Language requirement: The user's question is in English. "
        "Write your entire answer in English."
    )


def has_internal_markers(text: str) -> bool:
    return bool(_INTERNAL_MARKER_RE.search(text or ""))


def sanitize_bedrock_answer(text: str) -> str:
    if not text:
        return text
    cleaned = _PASSAGE_MARKER_FULL_RE.sub("", text)
    cleaned = _PASSAGE_MARKER_SHORT_RE.sub("", cleaned)
    cleaned = re.sub(r"\bthe one highlighted in\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bhighlighted in\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bas noted in\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\bappears to be the one\s*\.",
        "could not be identified clearly from the documents.",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\bin\s+\.", ".", cleaned)
    cleaned = re.sub(r"\bin\s+,", ",", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    return cleaned.strip()


def _scoutmatch_allowed_uri_prefix() -> str:
    bucket = (config.AWS_S3_BUCKET or "").strip()
    prefix = config.normalised_s3_prefix()
    return f"s3://{bucket}/{prefix}".lower()


def _session_allowed_uri_prefix(session_id: str) -> str:
    bucket = (config.AWS_S3_BUCKET or "").strip()
    prefix = config.normalised_s3_prefix()
    return f"s3://{bucket}/{prefix}sessions/{session_id}/".lower()


def _is_allowed_scoutmatch_source(uri: str | None) -> bool:
    if not uri or not isinstance(uri, str):
        return False
    normalized = uri.strip().lower()
    if not normalized.startswith("s3://"):
        return False
    if not normalized.startswith(_scoutmatch_allowed_uri_prefix()):
        return False
    filename = Path(uri).name.lower()
    if filename in {"knowledge_test.txt", ".", ".."}:
        return False
    if "/data/" in normalized or normalized.endswith("/data"):
        return False
    stale_course = (
        "docker_aws.pdf",
        "flask-lecture",
        "for_check.txt",
        "avidan risk analysis",
    )
    if any(token in filename for token in stale_course):
        return False
    return True


def _is_allowed_session_source(uri: str | None, session_id: str | None) -> bool:
    if not session_id:
        return False
    if not _is_allowed_scoutmatch_source(uri):
        return False
    return str(uri).strip().lower().startswith(_session_allowed_uri_prefix(session_id))


def _filter_scoutmatch_results(
    results: list[dict],
    *,
    min_score: float | None,
    top_k: int | None = None,
    session_id: str | None = None,
) -> list[dict]:
    filtered: list[dict] = []
    for item in results:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        if session_id:
            if not _is_allowed_session_source(item.get("s3_uri"), session_id):
                continue
        elif not _is_allowed_scoutmatch_source(item.get("s3_uri")):
            continue
        score = item.get("score")
        if min_score is not None:
            if score is None or float(score) < min_score:
                continue
        filtered.append(item)
    filtered.sort(key=lambda row: row.get("score") or 0.0, reverse=True)
    if top_k is not None:
        return filtered[:top_k]
    return filtered


def _chunk_source_filename(chunk: dict) -> str:
    return (
        chunk.get("source")
        or _display_name_from_uri(chunk.get("s3_uri") or "")
    ).lower()


def _canonical_source_key(filename: str) -> str:
    stem = Path(filename).stem.lower()
    return re.sub(r"_\d{8}_\d{6}$", "", stem)


def _is_timestamped_source_filename(filename: str) -> bool:
    return bool(re.search(r"_\d{8}_\d{6}$", Path(filename).stem))


def _is_team_requirements_chunk(chunk: dict) -> bool:
    return "team_requirements" in _chunk_source_filename(chunk)


def _is_scouting_report_chunk(chunk: dict) -> bool:
    fn = _chunk_source_filename(chunk)
    uri = (chunk.get("s3_uri") or "").lower()
    return "_report" in fn or "scouting_reports" in uri


def _is_player_cv_chunk(chunk: dict) -> bool:
    fn = _chunk_source_filename(chunk)
    if _is_team_requirements_chunk(chunk) or _is_scouting_report_chunk(chunk):
        return False
    return any(fn.startswith(prefix) for prefix in _POSITION_PREFIXES)


def _is_comparison_or_recommendation_question(question: str) -> bool:
    q = (question or "").lower()
    patterns = (
        "most suitable",
        "best match",
        "best candidate",
        "best fit",
        "best goalkeeper",
        "who is the",
        "who would",
        "recommend",
        "which goalkeeper",
        "which player",
        "compare",
        "comparison",
        "most appropriate",
        "strongest match",
        "מתאים ביותר",
        "מי מתאים",
        "מי השוער",
        "מי המועמד",
        "המועמד המתאים",
        "compare candidates",
    )
    return any(p in q for p in patterns)


def _is_recommendation_question(question: str) -> bool:
    if _is_named_player_profile_question(question):
        return False
    return _is_comparison_or_recommendation_question(question)


def _history_has_football_context(history: list | None) -> bool:
    if not history:
        return False
    combined = " ".join(
        (msg.get("content") or "") for msg in history[-6:]
    ).lower()
    return any(marker in combined for marker in _FOOTBALL_HISTORY_MARKERS)


def _is_follow_up_question(question: str) -> bool:
    q = (question or "").strip()
    if len(q.split()) > 14:
        return False
    lowered = q.lower()
    return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in _FOLLOW_UP_PATTERNS)


_NAMED_PLAYER_PROFILE_PATTERNS = (
    re.compile(
        r"^\s*who\s+is\s+(?P<name>[A-Za-z\u0590-\u05FF][\w\u0590-\u05FF\-']*(?:\s+[A-Za-z\u0590-\u05FF][\w\u0590-\u05FF\-']*){0,3})\s*[?.!]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*tell\s+me\s+about\s+(?P<name>[A-Za-z\u0590-\u05FF][\w\u0590-\u05FF\-']*(?:\s+[A-Za-z\u0590-\u05FF][\w\u0590-\u05FF\-']*){0,3})\s*[?.!]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*what\s+do\s+we\s+know\s+about\s+(?P<name>[A-Za-z\u0590-\u05FF][\w\u0590-\u05FF\-']*(?:\s+[A-Za-z\u0590-\u05FF][\w\u0590-\u05FF\-']*){0,3})\s*[?.!]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:give\s+me\s+)?(?:a\s+)?summary\s+of\s+(?P<name>" + _PLAYER_NAME_CAPTURE + r")\s*[?.!]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*what\s+is\s+(?P<name>" + _PLAYER_NAME_CAPTURE + r")(?:'s|s)?\s+position\s*[?.!]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*which\s+team\s+does\s+(?P<name>" + _PLAYER_NAME_CAPTURE + r")\s+play\s+for\s*[?.!]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*מי\s+(?:זה|הוא)\s+(?P<name>" + _PLAYER_NAME_CAPTURE + r")\s*[?.!]?\s*$",
    ),
    re.compile(
        r"^\s*ספר\s+לי\s+על\s+(?P<name>" + _PLAYER_NAME_CAPTURE + r")\s*[?.!]?\s*$",
    ),
    re.compile(
        r"^\s*מה\s+אנחנו\s+יודעים\s+על\s+(?P<name>" + _PLAYER_NAME_CAPTURE + r")\s*[?.!]?\s*$",
    ),
    re.compile(
        r"^\s*מה\s+התפקיד\s+של\s+(?P<name>" + _PLAYER_NAME_CAPTURE + r")\s*[?.!]?\s*$",
    ),
    re.compile(
        r"^\s*באיזו\s+קבוצה\s+(?P<name>" + _PLAYER_NAME_CAPTURE + r")\s+משחק\s*[?.!]?\s*$",
    ),
)


def _clean_profile_name(raw: str) -> str:
    name = (raw or "").strip().strip("?.!").strip()
    name = re.sub(
        r"^(the|player|candidate|שחקן|מועמד)\s+",
        "",
        name,
        flags=re.IGNORECASE,
    )
    return name.strip()


def _is_valid_profile_player_name(name: str) -> bool:
    cleaned = _clean_profile_name(name)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if lowered in _PROFILE_NAME_BLOCKLIST:
        return False
    if cleaned in _PROFILE_NAME_BLOCKLIST:
        return False
    return 1 <= len(cleaned.split()) <= 4


def _english_player_name(name: str) -> str:
    cleaned = _clean_profile_name(name)
    if not cleaned:
        return cleaned
    if cleaned in _HEBREW_TO_ENGLISH_PLAYER_NAMES:
        return _HEBREW_TO_ENGLISH_PLAYER_NAMES[cleaned]
    if _contains_hebrew(cleaned):
        return cleaned
    return " ".join(part.capitalize() for part in cleaned.split())


def _normalize_hebrew_profile_question_to_english(question: str) -> str | None:
    player = _extract_named_player_from_profile_question(question)
    if not player:
        return None
    english_name = _english_player_name(player)
    q = (question or "").strip()
    if re.match(r"^\s*מי\s+(?:זה|הוא)\s+", q):
        return f"Who is {english_name}?"
    if re.match(r"^\s*ספר\s+לי\s+על\s+", q):
        return f"Tell me about {english_name}."
    if re.match(r"^\s*מה\s+אנחנו\s+יודעים\s+על\s+", q):
        return f"What do we know about {english_name}?"
    if re.match(r"^\s*מה\s+התפקיד\s+של\s+", q):
        return f"What is {english_name}'s position?"
    if re.match(r"^\s*באיזו\s+קבוצה\s+", q):
        return f"Which team does {english_name} play for?"
    return f"Who is {english_name}?"


def _build_retrieval_queries(question: str, profile_player: str | None) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()

    def add(query: str | None) -> None:
        cleaned = (query or "").strip()
        if not cleaned:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        queries.append(cleaned)

    english_player = _english_player_name(profile_player) if profile_player else None
    if profile_player and english_player:
        add(_expand_named_player_retrieval_query(english_player))

    add(question)

    if _contains_hebrew(question):
        english_equivalent = _normalize_hebrew_profile_question_to_english(question)
        if english_equivalent:
            add(english_equivalent)
            english_from_equiv = _extract_named_player_from_profile_question(
                english_equivalent
            )
            if english_from_equiv:
                add(_expand_named_player_retrieval_query(english_from_equiv))

    return queries


def _dedupe_retrieved_chunks(chunks: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        key = (
            chunk.get("s3_uri") or chunk.get("source") or "",
            _normalize_chunk_text(chunk.get("text", ""))[:240],
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(chunk)
    return merged


def _extract_named_player_from_profile_question(question: str) -> str | None:
    q = (question or "").strip()
    if not q or _is_comparison_or_recommendation_question(question):
        return None
    for pattern in _NAMED_PLAYER_PROFILE_PATTERNS:
        match = pattern.match(q)
        if not match:
            continue
        name = _clean_profile_name(match.group("name"))
        if name and _is_valid_profile_player_name(name):
            return name
    return None


def _is_named_player_profile_question(question: str) -> bool:
    return _extract_named_player_from_profile_question(question) is not None


def _normalize_person_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _name_tokens(name: str) -> list[str]:
    return [token for token in _normalize_person_name(name).split() if len(token) > 1]


def _expand_named_player_retrieval_query(player_name: str) -> str:
    tokens = _name_tokens(player_name)
    filename_hint = "_".join(tokens)
    return (
        f"{player_name} player profile CV scouting report {filename_hint} "
        f"full name position age current club previous clubs professional experience "
        f"preferred foot salary expectation relocation willingness strengths"
    )


def _prefer_named_player_chunks(chunks: list[dict], player_name: str) -> list[dict]:
    tokens = _name_tokens(player_name)
    if not tokens:
        return chunks
    matching: list[dict] = []
    other: list[dict] = []
    for chunk in chunks:
        haystack = " ".join([
            _chunk_source_filename(chunk),
            chunk.get("text") or "",
            chunk.get("source") or "",
        ]).lower().replace("_", " ")
        if all(token in haystack for token in tokens):
            matching.append(chunk)
        else:
            other.append(chunk)
    return matching + other if matching else chunks


_NAMED_PLAYER_PROFILE_INSTRUCTION = (
    "This is a general player-profile question. Provide a concise grounded summary "
    "using only the retrieved ScoutMatch context. Include only facts explicitly "
    "present in the context, such as full name, position, age, current club, "
    "previous clubs, professional experience, preferred foot, salary expectation, "
    "relocation willingness, and scouting strengths. Do not invent missing details."
)


def _is_question_in_scoutmatch_domain(question: str, history: list | None = None) -> bool:
    q = (question or "").strip().lower()
    if not q:
        return False

    for entity in _OUT_OF_DOMAIN_ENTITIES:
        if entity in q:
            return False

    if _is_follow_up_question(question):
        if re.search(
            r"\b(cohen|levi|azulay|silva|daniel|yossi|omer|marco)\b",
            q,
            re.IGNORECASE,
        ):
            return True
        return _history_has_football_context(history)

    if any(keyword in q for keyword in _SCOUTMATCH_DOMAIN_KEYWORDS):
        return True

    if _is_comparison_or_recommendation_question(question):
        return True

    if re.search(
        r"\b(cohen|levi|azulay|silva|daniel|yossi|omer|marco)\b",
        q,
        re.IGNORECASE,
    ):
        return True

    if _is_named_player_profile_question(question):
        return True

    return False


def _normalize_chunk_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _chunks_are_near_duplicate(first: dict, second: dict) -> bool:
    left = _normalize_chunk_text(first.get("text", ""))
    right = _normalize_chunk_text(second.get("text", ""))
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) > 50 and shorter in longer:
        return True
    shorter_words = set(shorter.split())
    if len(shorter_words) < 5:
        return False
    overlap = len(shorter_words & set(longer.split())) / len(shorter_words)
    return overlap > 0.85


def _chunk_has_key_facts(chunk: dict) -> bool:
    text = (chunk.get("text") or "").lower()
    markers = (
        "compact fact profile summary",
        "years of professional experience",
        "professional experience:",
        "annual salary expectation",
        "relocation willingness",
        "build-up ability",
    )
    return sum(1 for marker in markers if marker in text) >= 2


def _chunk_source_rank(chunk: dict) -> tuple[int, int, float]:
    filename = _chunk_source_filename(chunk)
    return (
        1 if _chunk_has_key_facts(chunk) else 0,
        0 if _is_timestamped_source_filename(filename) else 1,
        chunk.get("score") or 0.0,
    )


def _rank_chunks_for_file(chunks: list[dict]) -> list[dict]:
    return sorted(chunks, key=_chunk_source_rank, reverse=True)


def _group_validated_chunks_by_file(
    results: list[dict],
    *,
    min_score: float | None,
    session_id: str | None = None,
) -> dict[str, list[dict]]:
    validated = _filter_scoutmatch_results(
        results,
        min_score=min_score,
        session_id=session_id,
    )
    grouped: dict[str, list[dict]] = {}
    for chunk in validated:
        canonical = _canonical_source_key(_chunk_source_filename(chunk))
        grouped.setdefault(canonical, []).append(chunk)
    for filename, chunks in grouped.items():
        grouped[filename] = _rank_chunks_for_file(chunks)
    return grouped


def _select_complete_diverse_context_chunks(
    results: list[dict],
    question: str,
    *,
    min_score: float | None = None,
    source_limit: int | None = None,
    session_id: str | None = None,
) -> list[dict]:
    grouped = _group_validated_chunks_by_file(
        results,
        min_score=min_score,
        session_id=session_id,
    )
    if not grouped:
        return []

    max_per_source = config.AWS_KB_MAX_CHUNKS_PER_SOURCE
    file_limit = source_limit or config.AWS_KB_CONTEXT_SOURCE_LIMIT
    best_by_file = {filename: chunks[0] for filename, chunks in grouped.items()}
    ranked = sorted(best_by_file.values(), key=_chunk_source_rank, reverse=True)
    max_total_chunks = file_limit * max_per_source

    if not _is_comparison_or_recommendation_question(question):
        selected: list[dict] = []
        for chunk in ranked:
            canonical = _canonical_source_key(_chunk_source_filename(chunk))
            for candidate in grouped[canonical][:1]:
                if not any(_chunks_are_near_duplicate(existing, candidate) for existing in selected):
                    selected.append(candidate)
            if len(selected) >= config.AWS_KB_TOP_K:
                break
        return selected[: config.AWS_KB_TOP_K]

    selected: list[dict] = []
    seen_files: set[str] = set()

    def _append_chunk(chunk: dict) -> bool:
        canonical = _canonical_source_key(_chunk_source_filename(chunk))
        same_file = [
            row for row in selected
            if _canonical_source_key(_chunk_source_filename(row)) == canonical
        ]
        if len(same_file) >= max_per_source:
            return False
        if any(_chunks_are_near_duplicate(existing, chunk) for existing in same_file):
            return False
        selected.append(chunk)
        return True

    for chunk in ranked:
        if not _is_team_requirements_chunk(chunk):
            continue
        canonical = _canonical_source_key(_chunk_source_filename(chunk))
        for candidate in grouped[canonical][:max_per_source]:
            _append_chunk(candidate)
        seen_files.add(canonical)
        break

    for chunk in ranked:
        canonical = _canonical_source_key(_chunk_source_filename(chunk))
        if canonical in seen_files or not _is_player_cv_chunk(chunk):
            continue
        for candidate in grouped[canonical][:max_per_source]:
            _append_chunk(candidate)
        seen_files.add(canonical)
        if len(seen_files) >= file_limit or len(selected) >= max_total_chunks:
            return selected[:max_total_chunks]

    for chunk in ranked:
        canonical = _canonical_source_key(_chunk_source_filename(chunk))
        if canonical in seen_files or not _is_scouting_report_chunk(chunk):
            continue
        for candidate in grouped[canonical][:max_per_source]:
            _append_chunk(candidate)
        seen_files.add(canonical)
        if len(seen_files) >= file_limit or len(selected) >= max_total_chunks:
            return selected[:max_total_chunks]

    for chunk in ranked:
        canonical = _canonical_source_key(_chunk_source_filename(chunk))
        if canonical in seen_files:
            continue
        for candidate in grouped[canonical][:max_per_source]:
            _append_chunk(candidate)
        seen_files.add(canonical)
        if len(seen_files) >= file_limit or len(selected) >= max_total_chunks:
            break

    return selected[:max_total_chunks]


def _select_diverse_context_chunks(
    results: list[dict],
    question: str,
    *,
    min_score: float | None = None,
    source_limit: int | None = None,
) -> list[dict]:
    return _select_complete_diverse_context_chunks(
        results,
        question,
        min_score=min_score,
        source_limit=source_limit,
    )


def build_grounded_context_block(
    chunks: list[dict],
    *,
    max_chars: int | None = None,
) -> str:
    limit = max_chars if max_chars is not None else config.AWS_KB_CONTEXT_EXCERPT_MAX
    parts: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        text = (chunk.get("text") or "").strip()
        if len(text) > limit:
            text = text[:limit] + "..."
        score = chunk.get("score")
        score_label = f"{float(score):.3f}" if score is not None else "n/a"
        filename = chunk.get("source") or _display_name_from_uri(chunk.get("s3_uri") or "")
        parts.append(
            f"[Source {index}]\n"
            f"File: {filename}\n"
            f"Score: {score_label}\n"
            f"Content: {text}"
        )
    return "\n\n".join(parts)


def _source_category_from_uri(uri: str) -> str:
    lower = (uri or "").lower()
    if "team_requirements" in lower:
        return "TEAM REQUIREMENTS"
    if "scouting_reports" in lower or "_report" in Path(uri).name.lower():
        return "SCOUT REPORT"
    return "PLAYER CV"


def chunks_to_source_cards(chunks: list[dict]) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()
    ranked = sorted(chunks, key=_chunk_source_rank, reverse=True)
    for chunk in ranked:
        if not _is_allowed_scoutmatch_source(chunk.get("s3_uri")):
            continue
        canonical = _canonical_source_key(_chunk_source_filename(chunk))
        if canonical in seen:
            continue
        raw_text = (chunk.get("text") or "").strip()
        text = sanitize_bedrock_answer(raw_text)
        excerpt = text[:500] + ("..." if len(text) > 500 else "")
        uri = chunk.get("s3_uri") or ""
        display = chunk.get("source") or _display_name_from_uri(uri)
        if _is_timestamped_source_filename(display):
            display = _canonical_source_key(display) + Path(display).suffix
        seen.add(canonical)
        sources.append({
            "text": excerpt,
            "source": display,
            "page": 0,
            "score": chunk.get("score"),
            "location": uri,
            "s3_uri": uri,
            "category": _source_category_from_uri(uri),
        })
    return sources


def _bedrock_model_id() -> str:
    arn = (config.BEDROCK_MODEL_ARN or "").strip()
    if "/foundation-model/" in arn:
        return arn.split("/foundation-model/", 1)[1]
    if "/inference-profile/" in arn:
        return arn.split("/inference-profile/", 1)[1]
    return arn


def _build_generation_user_message(
    question: str,
    context_block: str,
    history: list | None,
    extra_instruction: str | None = None,
    matrix_block: str | None = None,
) -> str:
    parts = [f"Retrieved ScoutMatch context:\n{context_block}"]
    if matrix_block:
        parts.append(matrix_block.strip())
    if history:
        conv = _build_conversation_history_text(history)
        if conv:
            parts.append(f"Recent conversation:\n{conv}")
    parts.append(f"Question:\n{question.strip()}")
    if extra_instruction:
        parts.append(extra_instruction.strip())
    return "\n\n".join(parts)


def _build_conversation_history_text(history: list | None) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for msg in history[-6:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _extract_player_names_from_sources(sources: list[dict]) -> set[str]:
    names: set[str] = set()
    for source in sources:
        text = source.get("text") or ""
        for match in _FULL_NAME_RE.finditer(text):
            name = match.group(1).strip()
            if name:
                names.add(name)
        stem = Path((source.get("source") or "").lower()).stem
        for prefix in _POSITION_PREFIXES:
            if stem.startswith(prefix):
                body = stem[len(prefix):].removesuffix("_report")
                parts = [p for p in body.split("_") if p]
                if len(parts) >= 2:
                    names.add(" ".join(part.capitalize() for part in parts))
    return names


def _answer_names_cited_player(answer: str, known_names: set[str]) -> bool:
    if not known_names:
        return True
    lowered = answer.lower()
    for name in known_names:
        if name.lower() in lowered:
            return True
        parts = name.split()
        if len(parts) >= 2 and parts[0].lower() in lowered and parts[-1].lower() in lowered:
            return True
        for variant in _PLAYER_NAME_VARIANTS.get(name.lower(), ()):
            if variant in answer:
                return True
    return False


def _answer_uses_vague_reference(answer: str) -> bool:
    vague_patterns = (
        r"\bthe candidate\b",
        r"\bthis candidate\b",
        r"\bthat candidate\b",
        r"\bthis player\b",
        r"\bthe player\b",
        r"\bthe one highlighted\b",
        r"\bhighlighted in\b",
        r"\bthe most suitable candidate\b",
    )
    return any(re.search(pattern, answer, re.IGNORECASE) for pattern in vague_patterns)


def _has_obvious_numeric_contradiction(answer: str) -> bool:
    lowered = answer.lower()
    if re.search(r"4\s+years?", lowered) and re.search(
        r"(at least|minimum of|min\.?)\s+5\s+years?", lowered
    ):
        if re.search(
            r"(meets|meet|satisf|fulfil|fulfill|matches|match(es)?)\s+(the\s+)?requirement",
            lowered,
        ):
            return True
    if re.search(r"90[,\s]?000", lowered) and re.search(
        r"(maximum|up to|at most|max\.?)\s+.*80[,\s]?000", lowered
    ):
        if re.search(r"(meets|within|satisf|under budget|fits)", lowered):
            return True
    return False


def _validate_answer_quality(
    question: str,
    answer: str,
    sources: list[dict],
    matrix: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    accepted, reason = validate_final_answer(question, answer, sources)
    if not accepted:
        return accepted, reason
    if matrix and matrix.get("has_active_requirements"):
        matrix_ok, matrix_reason = validate_answer_against_verified_matrix(
            answer, matrix
        )
        if not matrix_ok:
            return False, matrix_reason or "matrix_contradiction"
        exact_ok, exact_reason = validate_exact_match_acknowledgment(
            answer, matrix, question
        )
        if not exact_ok:
            return False, exact_reason or "exact_match_acknowledgment"
    return True, None


def _question_mentions_player(question: str, player_name: str) -> bool:
    lowered = question.lower()
    if player_name.lower() in lowered:
        return True
    parts = player_name.split()
    if len(parts) >= 2:
        if parts[0].lower() in lowered and parts[-1].lower() in lowered:
            return True
    for variant in _PLAYER_NAME_VARIANTS.get(player_name.lower(), ()):
        if variant in question:
            return True
    return False


def _extract_player_names_from_question(
    question: str,
    sources: list[dict],
) -> list[str]:
    """Return player names explicitly referenced in the user question."""
    known = _extract_player_names_from_sources(sources)
    matched = [
        name for name in known
        if _question_mentions_player(question, name)
    ]
    if matched:
        return matched

    for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", question):
        candidate = match.group(1).strip()
        if candidate:
            matched.append(candidate)
    return matched


def _extract_preferred_player_from_answer(
    answer: str,
    sources: list[dict],
) -> str | None:
    known = sorted(
        _extract_player_names_from_sources(sources),
        key=len,
        reverse=True,
    )
    preference_patterns = (
        r"preferred candidate",
        r"most suitable",
        r"strongest match",
        r"best (?:fit|candidate|match|choice)",
        r"top candidate",
        r"מועמד המועדף",
        r"המועמד המתאים",
        r"מתאים ביותר",
        r"המועמד המתאים ביותר",
    )
    for pattern in preference_patterns:
        for name in known:
            if re.search(
                rf"{pattern}.{{0,120}}{re.escape(name)}",
                answer,
                re.IGNORECASE | re.DOTALL,
            ):
                return name
            if re.search(
                rf"{re.escape(name)}.{{0,120}}{pattern}",
                answer,
                re.IGNORECASE | re.DOTALL,
            ):
                return name
    for name in known:
        if _answer_names_cited_player(answer, {name}):
            return name
    return None


def _main_source_for_player(
    sources: list[dict],
    player_name: str,
) -> dict | None:
    parts = player_name.lower().split()
    if len(parts) < 2:
        return None
    first, last = parts[0], parts[-1]

    cv_candidates: list[tuple[int, float, dict]] = []
    report_candidates: list[tuple[float, dict]] = []

    for source in sources:
        uri = source.get("s3_uri") or ""
        if uri and not _is_allowed_scoutmatch_source(uri):
            continue
        fn = _chunk_source_filename({
            "source": source.get("source"),
            "s3_uri": uri,
        })
        if first not in fn or last not in fn:
            continue
        score = float(source.get("score") or 0.0)
        if _is_scouting_report_chunk({"source": fn, "s3_uri": uri}):
            report_candidates.append((score, source))
            continue
        if _is_player_cv_chunk({"source": fn, "s3_uri": uri}):
            basename = Path(fn).name
            stem = Path(basename).stem.lower()
            prefer_rank = 2 if stem == _canonical_source_key(basename) else 1
            cv_candidates.append((prefer_rank, score, source))

    if cv_candidates:
        cv_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return cv_candidates[0][2]
    if report_candidates:
        report_candidates.sort(key=lambda item: item[0], reverse=True)
        return report_candidates[0][1]
    return None


def _infer_main_source_player(
    question: str,
    answer: str,
    verified_matrix: dict[str, Any] | None,
    sources: list[dict],
) -> str | None:
    question_players = _extract_player_names_from_question(question, sources)
    if len(question_players) == 1:
        return question_players[0]
    if len(question_players) > 1:
        for name in question_players:
            if re.search(r"(salary|שכר|wage|pay)", question, re.IGNORECASE):
                return name
        return question_players[0]

    if _is_recommendation_question(question) or (
        verified_matrix and verified_matrix.get("has_active_requirements")
    ):
        preferred = _extract_preferred_player_from_answer(answer, sources)
        if preferred:
            return preferred

    return None


def select_main_source(
    sources: list[dict],
    *,
    answer: str,
    question: str,
    verified_matrix: dict[str, Any] | None = None,
) -> dict | None:
    if not sources:
        return None

    validated = [
        source for source in sources
        if _is_allowed_scoutmatch_source(source.get("s3_uri") or "")
        or _is_allowed_scoutmatch_source(source.get("source") or "")
    ]
    pool = validated or list(sources)

    target_player = _infer_main_source_player(
        question,
        answer,
        verified_matrix,
        pool,
    )
    if target_player:
        preferred = _main_source_for_player(pool, target_player)
        if preferred:
            return preferred

    return max(pool, key=lambda item: float(item.get("score") or -1.0))


def _answer_mentions_profile_player(answer: str, profile_player: str) -> bool:
    if not profile_player:
        return True
    candidates = {profile_player, _english_player_name(profile_player)}
    answer_lower = (answer or "").lower()
    for name in candidates:
        tokens = _name_tokens(name)
        if tokens and all(token in answer_lower for token in tokens):
            return True
        if name and name in (answer or ""):
            return True
    english_key = _english_player_name(profile_player).lower()
    for variant in _PLAYER_NAME_VARIANTS.get(english_key, ()):
        if variant in (answer or ""):
            return True
    return False


def validate_final_answer(
    question: str,
    answer: str,
    sources: list[dict],
) -> tuple[bool, str | None]:
    if has_internal_markers(answer):
        return False, "internal_markers"
    if _has_obvious_numeric_contradiction(answer):
        return False, "numeric_contradiction"
    profile_player = _extract_named_player_from_profile_question(question)
    if profile_player:
        if _answer_mentions_profile_player(answer, profile_player):
            return True, None
        return False, "profile_name_missing"
    if _is_recommendation_question(question):
        known_names = _extract_player_names_from_sources(sources)
        if known_names and not _answer_names_cited_player(answer, known_names):
            return False, "no_explicit_name"
        if _answer_uses_vague_reference(answer):
            return False, "vague_recommendation"
    return True, None


def _build_bedrock_prompt_template(question: str) -> str:
    lang = _language_instruction_for_question(question)
    return (
        f"{lang}\n\n"
        f"{config.SCOUTMATCH_SYSTEM_PROMPT}\n\n"
        "$search_results$\n\n$query$"
    )


def _build_explicit_generation_system_prompt(question: str) -> str:
    lang = _language_instruction_for_question(question)
    return f"{lang}\n\n{EXPLICIT_GENERATION_PROMPT}"


def _strict_refusal_response(
    refusal: str,
    *,
    reason: str,
    context: list | None = None,
    bedrock_session_id: str | None = None,
) -> dict:
    return {
        "answer": refusal,
        "context": context or [],
        "refused": True,
        "reason": reason,
        "generation_mode": "aws_kb",
        "bedrock_session_id": bedrock_session_id,
    }


class AWSKnowledgeBaseEngine:
    """Bedrock Knowledge Base explicit retrieve-then-generate backend."""

    def __init__(self) -> None:
        self.chunks: list = []
        self.ready: bool = False
        self.status: str = "not_initialised"
        self.progress: dict = {"current": 0, "total": 0}
        self._lock = threading.Lock()
        self._runtime_client: Any = None
        self._bedrock_client: Any = None
        self._config_errors: list[str] = []

    def initialise(self) -> None:
        missing = config.validate_aws_config()
        if missing:
            raise ValueError(
                "Missing required AWS settings for ScoutMatch: "
                + ", ".join(missing)
            )
        with self._lock:
            if self.ready:
                return
            self.status = "initialising"
            self.progress = {"current": 0, "total": 1}
            self._config_errors = []
            self._runtime_client = boto3.client(
                "bedrock-agent-runtime",
                region_name=config.AWS_REGION,
            )
            self._bedrock_client = boto3.client(
                "bedrock-runtime",
                region_name=config.AWS_REGION,
            )
            self.ready = True
            self.status = "ready"
            self.progress = {"current": 1, "total": 1}

    def reindex(self) -> None:
        with self._lock:
            self.status = "ready"
            self.ready = True
            self.progress = {"current": 1, "total": 1}

    def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        *,
        candidates: int | None = None,
        session_id: str | None = None,
    ) -> list[dict]:
        if not self.ready or self._runtime_client is None:
            raise RuntimeError("AWS Knowledge Base engine is not ready yet.")
        if not session_id:
            return []
        k = candidates if candidates is not None else (
            top_k if top_k is not None else config.AWS_KB_RETRIEVE_CANDIDATES
        )
        vector_config: dict[str, Any] = {
            "numberOfResults": k,
            "filter": {
                "equals": {
                    "key": "session_id",
                    "value": session_id,
                }
            },
        }
        response = self._runtime_client.retrieve(
            knowledgeBaseId=config.BEDROCK_KB_ID.strip(),
            retrievalQuery={"text": question.strip()},
            retrievalConfiguration={
                "vectorSearchConfiguration": vector_config,
            },
        )
        results: list[dict] = []
        for item in response.get("retrievalResults") or []:
            content = item.get("content") or {}
            text = (content.get("text") or "").strip()
            score = item.get("score")
            location = item.get("location") or {}
            s3_uri, label = _location_fields(location)
            display = _display_name_from_uri(s3_uri or label)
            if not _is_allowed_session_source(s3_uri, session_id):
                continue
            results.append({
                "text": text,
                "source": display,
                "page": 0,
                "score": float(score) if score is not None else None,
                "location": label,
                "s3_uri": s3_uri,
            })
        return results

    def _retrieve_merged(
        self,
        queries: list[str],
        *,
        session_id: str,
    ) -> list[dict]:
        merged: list[dict] = []
        for query in queries:
            batch = self.retrieve(
                query,
                candidates=config.AWS_KB_RETRIEVE_CANDIDATES,
                session_id=session_id,
            )
            merged.extend(batch)
        return _dedupe_retrieved_chunks(merged)

    def _generate_from_retrieved_context(
        self,
        question: str,
        context_block: str,
        history: list | None = None,
        *,
        extra_instruction: str | None = None,
        matrix_block: str | None = None,
    ) -> str:
        if not self._bedrock_client:
            raise RuntimeError("Bedrock runtime client is not ready yet.")
        user_message = _build_generation_user_message(
            question,
            context_block,
            history,
            extra_instruction,
            matrix_block,
        )
        response = self._bedrock_client.converse(
            modelId=_bedrock_model_id(),
            system=[{"text": _build_explicit_generation_system_prompt(question)}],
            messages=[{
                "role": "user",
                "content": [{"text": user_message}],
            }],
            inferenceConfig={"maxTokens": 2048, "temperature": 0.1},
        )
        blocks = response.get("output", {}).get("message", {}).get("content") or []
        parts = [block.get("text", "") for block in blocks if block.get("text")]
        return "\n".join(parts).strip()

    def _generate_with_single_name_retry(
        self,
        question: str,
        context_block: str,
        history: list | None,
        *,
        matrix_block: str | None = None,
    ) -> str:
        return self._generate_from_retrieved_context(
            question,
            context_block,
            history,
            extra_instruction=_NAME_RETRY_INSTRUCTION,
            matrix_block=matrix_block,
        )

    def _generate_with_matrix_retry(
        self,
        question: str,
        context_block: str,
        history: list | None,
        *,
        matrix_block: str | None = None,
    ) -> str:
        return self._generate_from_retrieved_context(
            question,
            context_block,
            history,
            extra_instruction=MATRIX_CONTRADICTION_RETRY_INSTRUCTION,
            matrix_block=matrix_block,
        )

    def _generate_with_exact_match_retry(
        self,
        question: str,
        context_block: str,
        history: list | None,
        *,
        matrix_block: str | None = None,
    ) -> str:
        return self._generate_from_retrieved_context(
            question,
            context_block,
            history,
            extra_instruction=EXACT_MATCH_ACKNOWLEDGMENT_RETRY_INSTRUCTION,
            matrix_block=matrix_block,
        )

    def answer(
        self,
        question: str,
        history: list | None = None,
        k: int | None = None,
        app_session_id: str | None = None,
        bedrock_session_id: str | None = None,
    ) -> dict:
        if not question or not question.strip():
            return {
                "answer": "Please type a real question.",
                "context": [],
                "refused": True,
                "reason": "empty_question",
                "generation_mode": "aws_kb",
            }

        if not self.ready or self._runtime_client is None:
            raise RuntimeError("AWS Knowledge Base engine is not ready yet.")

        refusal = _refusal_text(question)
        min_score = config.AWS_KB_MIN_SCORE_FLOAT

        if not app_session_id:
            return _strict_refusal_response(refusal, reason="missing_session_id")

        if not _is_question_in_scoutmatch_domain(question, history):
            return _strict_refusal_response(refusal, reason="out_of_domain")

        profile_player = _extract_named_player_from_profile_question(question)
        retrieval_queries = _build_retrieval_queries(question, profile_player)

        try:
            if len(retrieval_queries) <= 1:
                retrieved = self.retrieve(
                    retrieval_queries[0] if retrieval_queries else question,
                    candidates=config.AWS_KB_RETRIEVE_CANDIDATES,
                    session_id=app_session_id,
                )
            else:
                retrieved = self._retrieve_merged(
                    retrieval_queries,
                    session_id=app_session_id,
                )
        except Exception as exc:
            logger.error("Bedrock retrieve failed: %s", exc.__class__.__name__)
            return {
                "answer": refusal,
                "context": [],
                "refused": True,
                "reason": "retrieve_error",
                "generation_mode": "aws_kb",
            }

        if not retrieved:
            return _strict_refusal_response(refusal, reason="no_scoutmatch_sources")

        validated = _select_complete_diverse_context_chunks(
            retrieved,
            question,
            min_score=min_score,
            session_id=app_session_id,
        )

        if not validated:
            return _strict_refusal_response(
                refusal,
                reason="no_scoutmatch_sources",
            )

        if profile_player:
            prefer_name = _english_player_name(profile_player)
            validated = _prefer_named_player_chunks(validated, prefer_name)

        context_block = build_grounded_context_block(validated)
        if not context_block.strip():
            return _strict_refusal_response(refusal, reason="empty_context")

        verified_matrix: dict[str, Any] | None = None
        matrix_block = ""
        player_facts = extract_verified_player_facts(validated)
        if should_build_verified_matrix(question, player_facts):
            requirements = extract_recruitment_requirements(question)
            verified_matrix = build_verified_candidate_matrix(
                player_facts,
                requirements,
            )
            matrix_block = format_verified_matrix_for_prompt(verified_matrix)

        profile_instruction = (
            _NAMED_PLAYER_PROFILE_INSTRUCTION if profile_player else None
        )
        try:
            answer_text = self._generate_from_retrieved_context(
                question,
                context_block,
                history,
                extra_instruction=profile_instruction,
                matrix_block=matrix_block or None,
            )
        except Exception as exc:
            logger.error("Bedrock generation failed: %s", exc.__class__.__name__)
            return _strict_refusal_response(
                refusal,
                reason="generation_error",
                context=chunks_to_source_cards(validated),
            )

        if not answer_text or _looks_like_refusal(answer_text):
            return _strict_refusal_response(
                refusal,
                reason="model_refusal",
                context=chunks_to_source_cards(validated),
            )

        sources = chunks_to_source_cards(validated)
        if not sources:
            return _strict_refusal_response(refusal, reason="no_sources")

        answer_text = sanitize_bedrock_answer(answer_text)
        if not answer_text or _looks_like_refusal(answer_text):
            return _strict_refusal_response(
                refusal,
                reason="model_refusal",
                context=sources,
            )

        accepted, quality_reason = _validate_answer_quality(
            question, answer_text, sources, verified_matrix
        )
        matrix_retry_used = False
        exact_match_retry_used = False
        name_retry_used = False
        used_exact_match_fallback = False

        if (
            not accepted
            and quality_reason == "matrix_contradiction"
            and verified_matrix
            and verified_matrix.get("has_active_requirements")
        ):
            try:
                retry_text = self._generate_with_matrix_retry(
                    question,
                    context_block,
                    history,
                    matrix_block=matrix_block or None,
                )
            except Exception as exc:
                logger.error(
                    "Bedrock matrix-retry generation failed: %s",
                    exc.__class__.__name__,
                )
                return _strict_refusal_response(
                    refusal,
                    reason="matrix_contradiction",
                    context=sources,
                )
            matrix_retry_used = True
            retry_text = sanitize_bedrock_answer(retry_text)
            if retry_text and not _looks_like_refusal(retry_text):
                accepted, quality_reason = _validate_answer_quality(
                    question, retry_text, sources, verified_matrix
                )
                if accepted:
                    answer_text = retry_text

        if (
            not accepted
            and quality_reason == "exact_match_acknowledgment"
            and verified_matrix
            and verified_matrix.get("has_active_requirements")
            and not exact_match_retry_used
        ):
            try:
                retry_text = self._generate_with_exact_match_retry(
                    question,
                    context_block,
                    history,
                    matrix_block=matrix_block or None,
                )
            except Exception as exc:
                logger.error(
                    "Bedrock exact-match retry generation failed: %s",
                    exc.__class__.__name__,
                )
            else:
                exact_match_retry_used = True
                retry_text = sanitize_bedrock_answer(retry_text)
                if retry_text and not _looks_like_refusal(retry_text):
                    accepted, quality_reason = _validate_answer_quality(
                        question, retry_text, sources, verified_matrix
                    )
                    if accepted:
                        answer_text = retry_text

        if (
            not accepted
            and quality_reason == "no_explicit_name"
            and _is_recommendation_question(question)
            and not name_retry_used
        ):
            try:
                retry_text = self._generate_with_single_name_retry(
                    question,
                    context_block,
                    history,
                    matrix_block=matrix_block or None,
                )
            except Exception as exc:
                logger.error(
                    "Bedrock name-retry generation failed: %s",
                    exc.__class__.__name__,
                )
                return _strict_refusal_response(
                    refusal,
                    reason=quality_reason or "answer_quality",
                    context=sources,
                )
            name_retry_used = True
            retry_text = sanitize_bedrock_answer(retry_text)
            if retry_text and not _looks_like_refusal(retry_text):
                accepted, quality_reason = _validate_answer_quality(
                    question, retry_text, sources, verified_matrix
                )
                if accepted:
                    answer_text = retry_text

        if (
            not accepted
            and quality_reason == "exact_match_acknowledgment"
            and verified_matrix
        ):
            fallback = build_safe_exact_match_fallback(verified_matrix, question)
            if fallback:
                answer_text = fallback
                accepted = True
                quality_reason = None
                used_exact_match_fallback = True

        if not accepted:
            logger.warning(
                "Answer rejected by runtime quality check: %s", quality_reason
            )
            return _strict_refusal_response(
                refusal,
                reason=quality_reason or "answer_quality",
                context=sources,
            )

        generation_mode = "aws_kb"
        if used_exact_match_fallback:
            generation_mode = "aws_kb_exact_match_fallback"

        return {
            "answer": answer_text,
            "context": sources,
            "main_source": select_main_source(
                sources,
                answer=answer_text,
                question=question,
                verified_matrix=verified_matrix,
            ),
            "refused": False,
            "reason": None,
            "generation_mode": generation_mode,
            "bedrock_session_id": bedrock_session_id,
        }

    def retrieve_and_generate_diagnostic(
        self,
        question: str,
        history: list | None = None,
        app_session_id: str | None = None,
        bedrock_session_id: str | None = None,
    ) -> dict:
        """Legacy retrieve_and_generate — diagnostics only."""
        if not self.ready or self._runtime_client is None:
            raise RuntimeError("AWS Knowledge Base engine is not ready yet.")
        if not app_session_id:
            raise RuntimeError("A session ID is required for AWS Knowledge Base retrieval.")
        prompt_with_history = _build_question_with_history(question, history)
        gen_config: dict[str, Any] = {
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": config.BEDROCK_KB_ID.strip(),
                "modelArn": config.BEDROCK_MODEL_ARN.strip(),
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {
                        "numberOfResults": config.AWS_KB_TOP_K,
                        "filter": {
                            "equals": {
                                "key": "session_id",
                                "value": app_session_id,
                            }
                        },
                    },
                },
                "generationConfiguration": {
                    "promptTemplate": {
                        "textPromptTemplate": _build_bedrock_prompt_template(question),
                    },
                },
            },
        }
        request: dict[str, Any] = {
            "input": {"text": prompt_with_history},
            "retrieveAndGenerateConfiguration": gen_config,
        }
        if bedrock_session_id:
            request["sessionId"] = bedrock_session_id
        return self._runtime_client.retrieve_and_generate(**request)


def extract_sources_from_citations(citations: list) -> list[dict]:
    sources: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for citation in citations or []:
        refs = citation.get("retrievedReferences") or citation.get(
            "retrieved_references", []
        )
        for ref in refs:
            content = ref.get("content") or {}
            text = (content.get("text") or "").strip()
            location = ref.get("location") or {}
            s3_uri, location_label = _location_fields(location)
            if not _is_allowed_scoutmatch_source(s3_uri):
                continue
            display = _display_name_from_uri(s3_uri or location_label)
            key = (s3_uri or location_label, text[:200])
            if key in seen:
                continue
            seen.add(key)
            sources.append({
                "text": sanitize_bedrock_answer(text),
                "source": display,
                "page": 0,
                "score": None,
                "location": location_label,
                "s3_uri": s3_uri,
                "category": _source_category_from_uri(s3_uri or ""),
            })
    return sources


def _build_question_with_history(question: str, history: list | None) -> str:
    if not history:
        return question.strip()
    lines: list[str] = []
    for msg in history[-10:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    if not lines:
        return question.strip()
    return (
        "Previous conversation:\n"
        + "\n".join(lines)
        + f"\n\nCurrent question: {question.strip()}"
    )


def _display_name_from_uri(uri_or_path: str) -> str:
    if not uri_or_path:
        return "unknown"
    if uri_or_path.startswith("s3://"):
        return Path(uri_or_path).name
    return Path(uri_or_path.replace("\\", "/")).name


def _location_fields(location: dict) -> tuple[str, str]:
    loc_type = location.get("type", "")
    parts: list[str] = []
    s3 = location.get("s3Location") or location.get("s3_location") or {}
    uri = (s3.get("uri") or "").strip()
    if uri:
        parts.append(uri)
    web = location.get("webLocation") or location.get("web_location") or {}
    if web.get("url"):
        parts.append(str(web["url"]))
    custom = location.get("customDocumentLocation") or location.get(
        "custom_document_location", {}
    )
    if custom.get("id"):
        parts.append(str(custom["id"]))
    label = " | ".join(parts) if parts else (loc_type or "unknown")
    return uri, label
