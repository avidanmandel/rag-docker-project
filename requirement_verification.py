"""
Deterministic requirement verification for ScoutMatch recruitment answers.

Parses verified facts from retrieved context, compares against user-stated
requirements, and validates generated answers against the backend matrix.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

RequirementStatus = Literal["PASS", "FAIL", "UNKNOWN"]

_EXPERIENCE_RE = re.compile(
    r"(?:Professional Experience:\s*(\d+)\s*years?"
    r"|Years of Professional Experience:\s*(\d+))",
    re.IGNORECASE,
)
_SALARY_RE = re.compile(
    r"Annual Salary Expectation:\s*([\d,]+)\s*EUR",
    re.IGNORECASE,
)
_RELOCATION_RE = re.compile(
    r"Relocation Willingness:\s*(YES|NO|MAYBE)",
    re.IGNORECASE,
)
_BUILDUP_RE = re.compile(
    r"Build-up Ability:\s*(Strong|Limited|Inconsistent)",
    re.IGNORECASE,
)
_CALM_RE = re.compile(
    r"Calmness Under Pressure:\s*(Strong|Limited|Variable)",
    re.IGNORECASE,
)
_FOOT_RE = re.compile(
    r"Preferred Foot:\s*(Right|Left)",
    re.IGNORECASE,
)
_FULL_NAME_RE = re.compile(
    r"Full Name:\s*(.+?)(?:\s*\||\n|$)",
    re.IGNORECASE,
)
_POSITION_RE = re.compile(r"Position:\s*(.+?)(?:\n|$)", re.IGNORECASE)

_BUILDUP_NARRATIVE_PATTERNS = (
    r"build-up specialist",
    r"build-up goalkeeper specialist",
    r"build-up goalkeeper",
    r"comfortable receiving back-passes",
    r"comfortable receiving under pressure",
    r"strong distribution under pressure",
    r"accurate short passing under pressure",
    r"plays out from the back",
    r"strong with the ball at his feet",
)

_CALM_NARRATIVE_PATTERNS = (
    r"composed under pressure",
    r"calm under pressure",
    r"composure under high press",
    r"calm first touch",
    r"remains calm when pressed",
    r"confident under pressure",
)

_POSITION_PREFIXES = (
    "goalkeeper_",
    "defender_",
    "midfielder_",
    "forward_",
)

MATRIX_CONTRADICTION_RETRY_INSTRUCTION = (
    "Your previous answer contradicted the verified backend matrix. "
    "Rewrite the answer without changing any verified PASS, FAIL, or UNKNOWN status. "
    "Do not redo arithmetic. Treat the matrix as authoritative."
)

EXACT_MATCH_ACKNOWLEDGMENT_RETRY_INSTRUCTION = (
    "Your previous draft contradicted the deterministic verified matrix or omitted "
    "an exact-match candidate.\n"
    "Rewrite the answer using only the uploaded ScoutMatch evidence and the verified matrix.\n"
    "Mention every candidate with all_mandatory_pass=YES by name.\n"
    "Do not describe a PASS requirement as missing, unknown, insufficient, or failed.\n"
    "Do not invent a tie-breaker.\n"
    "If the documents do not justify one preferred candidate, state that clearly."
)

PLAYER_NAME_VARIANTS: dict[str, tuple[str, ...]] = {
    "daniel cohen": ("דניאל כהן",),
    "yossi levi": ("יוסי לוי",),
    "omer azulay": ("עומר אזולאי",),
    "marco silva": ("מרקו סילבה",),
}

_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")

_CHECK_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "experience": ("experience", "years", "year", "ניסיון", "שנ"),
    "salary": ("salary", "שכר", "eur", "יורו", "אירו", "budget", "wage"),
    "relocation_north": ("reloc", "north", "צפון", "העבר", "northern"),
    "build_up": ("build-up", "build up", "feet", "משחק רגל", "הנעת", "buildup"),
    "calm_under_pressure": ("calm", "pressure", "לחץ", "רגוע", "composed", "stress"),
}

_PASS_NEGATION_PATTERNS = (
    r"does not meet",
    r"doesn't meet",
    r"do not meet",
    r"did not meet",
    r"not meet",
    r" fails ",
    r"failing",
    r"\blacks?\b",
    r"lack of",
    r"\bmissing\b",
    r"\bunknown\b",
    r"insufficient",
    r"unavailable",
    r"no information",
    r"no info",
    r"without evidence",
    r"not enough evidence",
    r"cannot confirm",
    r"can't confirm",
    r"אינו עומד",
    r"לא עומד",
    r"אינה עומדת",
    r"לא עומדת",
    r"אין מידע",
    r"חסר",
    r"לא מתאים",
    r"אינו מתאים",
    r"אינה מתאימה",
    r"לא מתאימה",
)

_MATRIX_PROMPT_RULES = """
VERIFIED MATRIX RULES (mandatory):
- Treat the VERIFIED REQUIREMENT MATRIX below as authoritative.
- Do not contradict any PASS, FAIL, or UNKNOWN status in the matrix.
- Do not redo arithmetic or re-evaluate numeric comparisons.
- Do not claim a candidate meets a requirement marked FAIL or UNKNOWN.
- If no candidate has all_mandatory_pass=YES, state clearly in Hebrew when answering in Hebrew:
  "לא נמצא מועמד שעומד בכל דרישות החובה."
- A closest partial match may be described only if every unmet requirement is listed.
- For recommendation or comparison questions:
  1. Read the verified matrix and identify EVERY candidate with all_mandatory_pass=YES.
  2. Briefly acknowledge each exact-match candidate before stating any preference.
  3. State a preferred recommendation ONLY when scouting reports or CVs provide meaningful distinguishing evidence.
  4. If two or more candidates satisfy all mandatory requirements and the documents do not provide enough evidence for a clear winner, state clearly (in Hebrew when answering in Hebrew) that there is more than one suitable candidate and the documents do not justify a definitive preference. Do not invent tie-breakers.
- Use uploaded ScoutMatch documents and the verified matrix only.
- Return the answer in the same language as the user.
- State player names explicitly using English names from the documents.
- Do not expose internal chain-of-thought or retrieval placeholders.
""".strip()


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.replace(",", "").strip())
    except ValueError:
        return None


def _normalize_line_endings(text: str) -> str:
    """Normalize CR/CRLF line endings to LF before regex parsing."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _canonical_player_key(filename: str) -> str:
    stem = Path(filename).stem.lower()
    return re.sub(r"_\d{8}_\d{6}$", "", stem)


def _name_from_filename(filename: str) -> str | None:
    stem = _canonical_player_key(filename)
    for prefix in _POSITION_PREFIXES:
        if stem.startswith(prefix):
            body = stem[len(prefix):]
            parts = [part for part in body.split("_") if part]
            if len(parts) >= 2:
                return " ".join(part.capitalize() for part in parts)
    return None


def _merge_text_fields(existing: str | None, new: str) -> str:
    if not existing:
        return new
    if new in existing:
        return existing
    return existing + "\n" + new


def _infer_build_up_from_narrative(text: str) -> str | None:
    lowered = text.lower()
    if any(re.search(pattern, lowered) for pattern in _BUILDUP_NARRATIVE_PATTERNS):
        return "Strong"
    return None


def _infer_calm_from_narrative(text: str) -> str | None:
    lowered = text.lower()
    if any(re.search(pattern, lowered) for pattern in _CALM_NARRATIVE_PATTERNS):
        return "Strong"
    return None


def _parse_facts_from_text(text: str) -> dict[str, Any]:
    text = _normalize_line_endings(text)
    facts: dict[str, Any] = {}
    exp = _EXPERIENCE_RE.search(text)
    if exp:
        facts["professional_experience_years"] = _parse_int(exp.group(1) or exp.group(2))
    salary = _SALARY_RE.search(text)
    if salary:
        facts["annual_salary_eur"] = _parse_int(salary.group(1))
    relocation = _RELOCATION_RE.search(text)
    if relocation:
        facts["relocation_north"] = relocation.group(1).upper()
    buildup = _BUILDUP_RE.search(text)
    if buildup:
        facts["build_up_ability"] = buildup.group(1).capitalize()
    elif (inferred_build_up := _infer_build_up_from_narrative(text)):
        facts["build_up_ability"] = inferred_build_up
    calm = _CALM_RE.search(text)
    if calm:
        facts["calm_under_pressure"] = calm.group(1).capitalize()
    elif (inferred_calm := _infer_calm_from_narrative(text)):
        facts["calm_under_pressure"] = inferred_calm
    foot = _FOOT_RE.search(text)
    if foot:
        facts["dominant_foot"] = foot.group(1).capitalize()
    name = _FULL_NAME_RE.search(text)
    if name:
        facts["full_name"] = name.group(1).strip()
    position = _POSITION_RE.search(text)
    if position:
        facts["position"] = position.group(1).strip()
    return facts


def _merge_player_fact(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if value is None:
            continue
        if key == "source_filenames":
            for filename in value:
                if filename not in target["source_filenames"]:
                    target["source_filenames"].append(filename)
            continue
        if target.get(key) is None:
            target[key] = value


def extract_verified_player_facts(chunks: list[dict]) -> list[dict[str, Any]]:
    """Parse grounded player facts from validated ScoutMatch context chunks."""
    combined_text: dict[str, str] = {}
    source_names: dict[str, list[str]] = {}

    for chunk in chunks:
        filename = (
            chunk.get("source")
            or Path(chunk.get("s3_uri") or "").name
        ).lower()
        if not any(filename.startswith(prefix) for prefix in _POSITION_PREFIXES):
            continue
        if "_report" in filename:
            continue

        text = (chunk.get("text") or "").strip()
        if not text:
            continue

        key = _canonical_player_key(filename)
        combined_text[key] = _merge_text_fields(combined_text.get(key), text)
        source_names.setdefault(key, [])
        basename = Path(filename).name
        if basename not in source_names[key]:
            source_names[key].append(basename)

    grouped: dict[str, dict[str, Any]] = {}
    for key, text in combined_text.items():
        parsed = _parse_facts_from_text(text)
        grouped[key] = {
            "full_name": parsed.get("full_name") or _name_from_filename(key + ".txt"),
            "position": parsed.get("position"),
            "professional_experience_years": parsed.get("professional_experience_years"),
            "annual_salary_eur": parsed.get("annual_salary_eur"),
            "relocation_north": parsed.get("relocation_north"),
            "build_up_ability": parsed.get("build_up_ability"),
            "calm_under_pressure": parsed.get("calm_under_pressure"),
            "dominant_foot": parsed.get("dominant_foot"),
            "source_filenames": source_names.get(key, []),
        }

    players = list(grouped.values())
    players.sort(key=lambda row: (row.get("full_name") or "").lower())
    return players


def extract_recruitment_requirements(question: str) -> dict[str, Any]:
    """Extract only explicitly stated recruitment requirements from the question."""
    q = (question or "").strip()
    lowered = q.lower()
    requirements: dict[str, Any] = {
        "min_experience_years": None,
        "max_salary_eur": None,
        "relocation_north_required": False,
        "build_up_required": False,
        "calm_under_pressure_required": False,
        "position": None,
    }

    for pattern in (
        r"לפחות\s+(\d+)\s+שנת",
        r"לפחות\s+(\d+)\s+שנות",
        r"(?:at least|minimum of|minimum)\s+(\d+)\s+years?",
    ):
        match = re.search(pattern, q, re.IGNORECASE)
        if match:
            requirements["min_experience_years"] = int(match.group(1))
            break

    for pattern in (
        r"שכר(?:ו)?\s+עד\s+([\d,]+)\s*(?:אירו|יורו|eur)?",
        r"(?:up to|maximum of|maximum|max\.?)\s+([\d,]+)\s*(?:eur|€)?",
    ):
        match = re.search(pattern, q, re.IGNORECASE)
        if match:
            requirements["max_salary_eur"] = _parse_int(match.group(1))
            break

    if any(
        phrase in q
        for phrase in (
            "מוכן לעבור לצפון",
            "לעבור לצפון",
            "relocate to north",
            "relocation to north",
            "relocate north",
            "northern england",
        )
    ):
        requirements["relocation_north_required"] = True

    if any(
        phrase in lowered or phrase in q
        for phrase in (
            "טוב במשחק רגל",
            "build-up",
            "build up",
            "good with his feet",
            "with feet",
            "משחק רגל",
        )
    ):
        requirements["build_up_required"] = True

    if any(
        phrase in lowered or phrase in q
        for phrase in (
            "רגוע תחת לחץ",
            "calm under pressure",
            "composed under pressure",
        )
    ):
        requirements["calm_under_pressure_required"] = True

    if "שוער" in q or "goalkeeper" in lowered:
        requirements["position"] = "goalkeeper"

    return requirements


def _status_experience(years: int | None, minimum: int | None) -> RequirementStatus:
    if minimum is None:
        return "PASS"
    if years is None:
        return "UNKNOWN"
    return "PASS" if years >= minimum else "FAIL"


def _status_salary(salary: int | None, maximum: int | None) -> RequirementStatus:
    if maximum is None:
        return "PASS"
    if salary is None:
        return "UNKNOWN"
    return "PASS" if salary <= maximum else "FAIL"


def _status_relocation(value: str | None, required: bool) -> RequirementStatus:
    if not required:
        return "PASS"
    if value is None:
        return "UNKNOWN"
    if value == "YES":
        return "PASS"
    if value in {"NO", "MAYBE"}:
        return "FAIL"
    return "UNKNOWN"


def _status_build_up(value: str | None, required: bool) -> RequirementStatus:
    if not required:
        return "PASS"
    if value is None:
        return "UNKNOWN"
    if value.lower() == "strong":
        return "PASS"
    if value.lower() in {"limited", "inconsistent"}:
        return "FAIL"
    return "UNKNOWN"


def _status_calm(value: str | None, required: bool) -> RequirementStatus:
    if not required:
        return "PASS"
    if value is None:
        return "UNKNOWN"
    if value.lower() == "strong":
        return "PASS"
    if value.lower() in {"limited", "variable"}:
        return "FAIL"
    return "UNKNOWN"


def build_verified_candidate_matrix(
    player_facts: list[dict[str, Any]],
    requirements: dict[str, Any],
) -> dict[str, Any]:
    """Build deterministic PASS/FAIL/UNKNOWN matrix for each candidate."""
    candidates: list[dict[str, Any]] = []
    active_requirements = [
        key for key, value in requirements.items()
        if key != "position" and value not in (None, False)
    ]

    for player in player_facts:
        checks: dict[str, RequirementStatus] = {
            "experience": _status_experience(
                player.get("professional_experience_years"),
                requirements.get("min_experience_years"),
            ),
            "salary": _status_salary(
                player.get("annual_salary_eur"),
                requirements.get("max_salary_eur"),
            ),
            "relocation_north": _status_relocation(
                player.get("relocation_north"),
                bool(requirements.get("relocation_north_required")),
            ),
            "build_up": _status_build_up(
                player.get("build_up_ability"),
                bool(requirements.get("build_up_required")),
            ),
            "calm_under_pressure": _status_calm(
                player.get("calm_under_pressure"),
                bool(requirements.get("calm_under_pressure_required")),
            ),
        }

        unmet: list[str] = []
        unknown: list[str] = []
        for req_key, status in checks.items():
            if requirements.get("min_experience_years") is None and req_key == "experience":
                continue
            if requirements.get("max_salary_eur") is None and req_key == "salary":
                continue
            if not requirements.get("relocation_north_required") and req_key == "relocation_north":
                continue
            if not requirements.get("build_up_required") and req_key == "build_up":
                continue
            if not requirements.get("calm_under_pressure_required") and req_key == "calm_under_pressure":
                continue
            if status == "FAIL":
                unmet.append(req_key)
            elif status == "UNKNOWN":
                unknown.append(req_key)

        mandatory_checks = [
            status for key, status in checks.items()
            if not (
                (key == "experience" and requirements.get("min_experience_years") is None)
                or (key == "salary" and requirements.get("max_salary_eur") is None)
                or (key == "relocation_north" and not requirements.get("relocation_north_required"))
                or (key == "build_up" and not requirements.get("build_up_required"))
                or (key == "calm_under_pressure" and not requirements.get("calm_under_pressure_required"))
            )
        ]
        all_pass = bool(mandatory_checks) and all(
            status == "PASS" for status in mandatory_checks
        )

        candidates.append({
            "player_name": player.get("full_name") or "Unknown",
            "raw_values": {
                "professional_experience_years": player.get("professional_experience_years"),
                "annual_salary_eur": player.get("annual_salary_eur"),
                "relocation_north": player.get("relocation_north"),
                "build_up_ability": player.get("build_up_ability"),
                "calm_under_pressure": player.get("calm_under_pressure"),
                "dominant_foot": player.get("dominant_foot"),
                "position": player.get("position"),
            },
            "checks": checks,
            "unmet_requirements": unmet,
            "unknown_requirements": unknown,
            "all_mandatory_pass": all_pass if mandatory_checks else False,
            "source_filenames": list(player.get("source_filenames") or []),
        })

    return {
        "requirements": requirements,
        "candidates": candidates,
        "has_active_requirements": bool(active_requirements),
    }


def format_verified_matrix_for_prompt(matrix: dict[str, Any]) -> str:
    """Render matrix for inclusion in the generation prompt."""
    if not matrix.get("candidates"):
        return ""

    lines = [
        "VERIFIED REQUIREMENT MATRIX — DETERMINISTIC BACKEND RESULT",
        _MATRIX_PROMPT_RULES,
        "",
        "Requirements extracted from user question:",
    ]
    reqs = matrix.get("requirements") or {}
    for key, value in reqs.items():
        if value not in (None, False):
            lines.append(f"- {key}: {value}")

    for row in matrix["candidates"]:
        lines.append("")
        lines.append(f"Candidate: {row['player_name']}")
        raw = row["raw_values"]
        lines.append(
            f"  raw_values: experience={raw.get('professional_experience_years')}, "
            f"salary_eur={raw.get('annual_salary_eur')}, "
            f"relocation={raw.get('relocation_north')}, "
            f"build_up={raw.get('build_up_ability')}, "
            f"calm={raw.get('calm_under_pressure')}"
        )
        for check_name, status in row["checks"].items():
            lines.append(f"  {check_name}_status: {status}")
        lines.append(f"  all_mandatory_pass: {'YES' if row['all_mandatory_pass'] else 'NO'}")
        if row["unmet_requirements"]:
            lines.append(f"  unmet_requirements: {', '.join(row['unmet_requirements'])}")
        if row["unknown_requirements"]:
            lines.append(f"  unknown_requirements: {', '.join(row['unknown_requirements'])}")
        if row["source_filenames"]:
            lines.append(f"  sources: {', '.join(row['source_filenames'])}")

    exact_matches = [
        row["player_name"]
        for row in matrix["candidates"]
        if row.get("all_mandatory_pass")
    ]
    if exact_matches and matrix.get("has_active_requirements"):
        lines.append("")
        lines.append(
            "Exact-match candidates (all mandatory requirements PASS): "
            + ", ".join(exact_matches)
        )
        lines.append(
            "Your answer MUST briefly acknowledge every exact-match candidate "
            "listed above before stating any preference or uncertainty."
        )

    return "\n".join(lines)


def _answer_mentions_player(answer: str, player_name: str) -> bool:
    if player_name.lower() in answer.lower():
        return True
    parts = player_name.split()
    if len(parts) >= 2:
        if parts[0].lower() in answer.lower() and parts[-1].lower() in answer.lower():
            return True
    for variant in PLAYER_NAME_VARIANTS.get(player_name.lower(), ()):
        if variant in answer:
            return True
    return False


def is_recommendation_or_comparison_question(question: str) -> bool:
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
        "מי השוער",
        "מי המועמד",
        "המועמד המתאים",
        "מתאים ביותר",
        "compare candidates",
    )
    return any(pattern in q or pattern in (question or "") for pattern in patterns)


def get_exact_match_candidates(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every candidate with all_mandatory_pass=YES and verified fields."""
    if not matrix or not matrix.get("candidates"):
        return []

    exact_matches: list[dict[str, Any]] = []
    for row in matrix["candidates"]:
        if not row.get("all_mandatory_pass"):
            continue
        name = row.get("player_name") or "Unknown"
        exact_matches.append({
            "player_name": name,
            "hebrew_variants": list(PLAYER_NAME_VARIANTS.get(name.lower(), ())),
            "raw_values": dict(row.get("raw_values") or {}),
            "checks": dict(row.get("checks") or {}),
            "source_filenames": list(row.get("source_filenames") or []),
            "all_mandatory_pass": True,
        })
    return exact_matches


def _is_mandatory_check(check_name: str, requirements: dict[str, Any]) -> bool:
    if check_name == "experience":
        return requirements.get("min_experience_years") is not None
    if check_name == "salary":
        return requirements.get("max_salary_eur") is not None
    if check_name == "relocation_north":
        return bool(requirements.get("relocation_north_required"))
    if check_name == "build_up":
        return bool(requirements.get("build_up_required"))
    if check_name == "calm_under_pressure":
        return bool(requirements.get("calm_under_pressure_required"))
    return False


def _sentence_has_pass_negation(sentence: str) -> bool:
    return any(
        re.search(pattern, sentence, re.IGNORECASE)
        for pattern in _PASS_NEGATION_PATTERNS
    )


def _sentence_relates_to_check(sentence: str, check_name: str) -> bool:
    lowered = sentence.lower()
    return any(keyword in lowered or keyword in sentence for keyword in _CHECK_FIELD_KEYWORDS[check_name])


def _sentence_denies_all_mandatory_pass(sentence: str) -> bool:
    if not _sentence_has_pass_negation(sentence):
        return False
    if re.search(
        r"(?:all mandatory|all requirements|every requirement|כל הדרישות|דרישות החובה)",
        sentence,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"אינו עומד|לא עומד|does not meet all|doesn't meet all", sentence, re.IGNORECASE):
        return True
    return False


def validate_exact_match_acknowledgment(
    answer: str,
    matrix: dict[str, Any] | None,
    question: str,
) -> tuple[bool, str | None]:
    """Validate that every exact-match candidate is acknowledged without PASS contradictions."""
    if not matrix or not matrix.get("has_active_requirements"):
        return True, None
    if not is_recommendation_or_comparison_question(question):
        return True, None

    exact_matches = get_exact_match_candidates(matrix)
    if not exact_matches:
        return True, None

    for candidate in exact_matches:
        if not _answer_mentions_player(answer, candidate["player_name"]):
            return False, "exact_match_acknowledgment"

    requirements = matrix.get("requirements") or {}
    sentences = _split_sentences(answer)

    for candidate in exact_matches:
        name = candidate["player_name"]
        checks = candidate["checks"]

        for sentence in sentences:
            if not _answer_mentions_player(sentence, name):
                continue

            if _sentence_denies_all_mandatory_pass(sentence):
                return False, "exact_match_acknowledgment"

            for check_name, status in checks.items():
                if not _is_mandatory_check(check_name, requirements):
                    continue
                if status != "PASS":
                    continue
                if (
                    _sentence_has_pass_negation(sentence)
                    and _sentence_relates_to_check(sentence, check_name)
                ):
                    return False, "exact_match_acknowledgment"

    return True, None


def _question_is_hebrew(question: str) -> bool:
    return bool(_HEBREW_RE.search(question or ""))


def _format_candidate_facts_hebrew(name: str, raw: dict[str, Any]) -> str:
    parts: list[str] = []
    years = raw.get("professional_experience_years")
    if years is not None:
        parts.append(f"{years} שנות ניסיון")
    salary = raw.get("annual_salary_eur")
    if salary is not None:
        parts.append(f"שכר שנתי של {salary:,} אירו")
    if raw.get("relocation_north") == "YES":
        parts.append("מוכן לעבור לצפון")
    if raw.get("build_up_ability"):
        parts.append(f"יכולת משחק רגל: {raw['build_up_ability']}")
    if raw.get("calm_under_pressure"):
        parts.append(f"רגוע תחת לחץ: {raw['calm_under_pressure']}")
    if not parts:
        return name
    return f"{name}: " + ", ".join(parts)


def _format_candidate_facts_english(name: str, raw: dict[str, Any]) -> str:
    parts: list[str] = []
    years = raw.get("professional_experience_years")
    if years is not None:
        parts.append(f"{years} years of experience")
    salary = raw.get("annual_salary_eur")
    if salary is not None:
        parts.append(f"annual salary of {salary:,} EUR")
    if raw.get("relocation_north") == "YES":
        parts.append("willing to relocate north")
    if raw.get("build_up_ability"):
        parts.append(f"build-up ability: {raw['build_up_ability']}")
    if raw.get("calm_under_pressure"):
        parts.append(f"calm under pressure: {raw['calm_under_pressure']}")
    if not parts:
        return name
    return f"{name}: " + ", ".join(parts)


def build_safe_exact_match_fallback(
    matrix: dict[str, Any],
    question: str,
) -> str:
    """Build a concise deterministic answer from verified exact-match candidates."""
    exact_matches = get_exact_match_candidates(matrix)
    if not exact_matches:
        return ""

    hebrew = _question_is_hebrew(question)
    names = [candidate["player_name"] for candidate in exact_matches]

    if hebrew:
        if len(names) == 1:
            names_text = names[0]
        else:
            names_text = f"{names[0]} ו-{names[1]}" if len(names) == 2 else ", ".join(names[:-1]) + f" ו-{names[-1]}"
        lines = [
            f"על סמך המסמכים שהועלו ל-ScoutMatch, {names_text} עומדים בדרישות החובה שנבדקו.",
        ]
        for candidate in exact_matches:
            lines.append(
                _format_candidate_facts_hebrew(
                    candidate["player_name"],
                    candidate["raw_values"],
                )
            )
        if len(exact_matches) > 1:
            lines.append(
                "על סמך המידע הקיים אין מספיק מידע כדי לקבוע באופן חד-משמעי מי עדיף."
            )
        return " ".join(lines)

    if len(names) == 1:
        names_text = names[0]
    elif len(names) == 2:
        names_text = f"{names[0]} and {names[1]}"
    else:
        names_text = ", ".join(names[:-1]) + f", and {names[-1]}"
    lines = [
        (
            "Based on the uploaded ScoutMatch documents, "
            f"{names_text} meet the mandatory requirements checked."
        ),
    ]
    for candidate in exact_matches:
        lines.append(
            _format_candidate_facts_english(
                candidate["player_name"],
                candidate["raw_values"],
            )
        )
    if len(exact_matches) > 1:
        lines.append(
            "Based on the available documents, there is not enough information "
            "to determine a definitive preference."
        )
    return " ".join(lines)


def _sentence_has_negative_requirement(text: str) -> bool:
    lowered = text.lower()
    if re.search(
        r"(?:does not|doesn't|do not|not)\s+(?:meet|satisf|fulfil|fulfill|match)",
        lowered,
    ):
        return True
    if re.search(r"לא\s+עומד|אינו\s+עומד|לא\s+מתאים|אינו\s+מתאים", text):
        return True
    return False


def _sentence_has_positive_requirement(text: str) -> bool:
    lowered = text.lower()
    if re.search(
        r"(?:meets|meet|satisf|fulfil|fulfill|matches|within|fits|under budget)",
        lowered,
    ):
        return True
    if re.search(r"עומד\s+בדריש|מתאים\s+לדריש|עומד\s+בתק", text):
        return True
    return False


def _split_sentences(answer: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", answer)
    return [part.strip() for part in parts if part.strip()]


def validate_answer_against_verified_matrix(
    answer: str,
    matrix: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Reject answers that clearly contradict the verified backend matrix."""
    if not matrix or not matrix.get("candidates"):
        return True, None

    if not matrix.get("has_active_requirements"):
        return True, None

    sentences = _split_sentences(answer)
    any_exact_match = any(row["all_mandatory_pass"] for row in matrix["candidates"])

    for row in matrix["candidates"]:
        name = row["player_name"]
        if not _answer_mentions_player(answer, name):
            continue

        raw = row["raw_values"]
        checks = row["checks"]

        for sentence in sentences:
            if not _answer_mentions_player(sentence, name):
                continue

            exp_years = raw.get("professional_experience_years")
            min_exp = matrix["requirements"].get("min_experience_years")
            if (
                checks.get("experience") == "PASS"
                and exp_years is not None
                and min_exp is not None
                and str(exp_years) in sentence
                and _sentence_has_negative_requirement(sentence)
                and (str(min_exp) in sentence or "ניסיון" in sentence or "experience" in sentence.lower())
            ):
                return False, "matrix_contradiction"

            if (
                checks.get("experience") == "FAIL"
                and exp_years is not None
                and min_exp is not None
                and str(exp_years) in sentence
                and _sentence_has_positive_requirement(sentence)
                and (str(min_exp) in sentence or "ניסיון" in sentence or "experience" in sentence.lower())
            ):
                return False, "matrix_contradiction"

            salary = raw.get("annual_salary_eur")
            max_salary = matrix["requirements"].get("max_salary_eur")
            if salary is not None and max_salary is not None and str(salary) in sentence.replace(",", ""):
                if checks.get("salary") == "PASS" and _sentence_has_negative_requirement(sentence):
                    if "שכר" in sentence or "salary" in sentence.lower() or "eur" in sentence.lower():
                        return False, "matrix_contradiction"
                if checks.get("salary") == "FAIL" and _sentence_has_positive_requirement(sentence):
                    if "שכר" in sentence or "salary" in sentence.lower() or "eur" in sentence.lower():
                        return False, "matrix_contradiction"

            if checks.get("relocation_north") == "FAIL" and _sentence_has_positive_requirement(sentence):
                if any(token in sentence.lower() for token in ("reloc", "north", "צפון", "העבר")):
                    return False, "matrix_contradiction"

            if checks.get("relocation_north") == "PASS" and _sentence_has_negative_requirement(sentence):
                if any(token in sentence.lower() for token in ("reloc", "north", "צפון", "העבר")):
                    return False, "matrix_contradiction"

        if not row["all_mandatory_pass"] and row["unmet_requirements"]:
            for sentence in sentences:
                if not _answer_mentions_player(sentence, name):
                    continue
                if re.search(
                    r"(?:exact match|perfect match|עומד בכל|meets all|all requirements)",
                    sentence,
                    re.IGNORECASE,
                ):
                    return False, "matrix_contradiction"

    if not any_exact_match and re.search(
        r"(?:exact match|perfect match|עומד בכל הדרישות|meets all mandatory requirements)",
        answer,
        re.IGNORECASE,
    ):
        return False, "matrix_contradiction"

    lowered = answer.lower()
    if re.search(r"4\s+years?", lowered) and re.search(
        r"(?:at least|minimum of|min\.?)\s+5\s+years?", lowered
    ):
        if re.search(
            r"(?:meets|meet|satisf|fulfil|fulfill|matches|match(es)?)\s+(?:the\s+)?requirement",
            lowered,
        ):
            return False, "matrix_contradiction"

    if re.search(r"90[,\s]?000", lowered) and re.search(
        r"(?:maximum|up to|at most|max\.?)\s+.*80[,\s]?000", lowered
    ):
        if re.search(r"(?:meets|within|satisf|under budget|fits)", lowered):
            return False, "matrix_contradiction"

    if (
        re.search(r"6\s+years?", lowered)
        and re.search(r"(?:at least|minimum of|min\.?)\s+5\s+years?", lowered)
        and re.search(
            r"(?:does not|doesn't|do not|not)\s+(?:meet|satisf)",
            lowered,
        )
    ):
        return False, "matrix_contradiction"

    if "6 שנ" in answer and "5" in answer and re.search(r"לא\s+עומד", answer):
        return False, "matrix_contradiction"

    return True, None


def should_build_verified_matrix(question: str, player_facts: list[dict[str, Any]]) -> bool:
    if not player_facts:
        return False
    lowered = (question or "").lower()
    markers = (
        "most suitable",
        "best goalkeeper",
        "recommend",
        "compare",
        "מי השוער",
        "מי המועמד",
        "מתאים ביותר",
        "recruit",
        "requirements",
        "ניסיון",
        "experience",
        "salary",
        "שכר",
    )
    return any(marker in lowered or marker in question for marker in markers)
