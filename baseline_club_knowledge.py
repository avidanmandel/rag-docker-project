"""
Baseline club knowledge parsing and deterministic answer helpers.

Read-only club documents are available in every conversation. Session-scoped
candidate uploads remain isolated per conversation.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

from requirement_verification import (
    _HEBREW_RE,
    _format_eur,
    _parse_int,
    _parse_facts_from_text,
)

_NAME_LINE_RE = re.compile(r"^(?:Full Name|Name):\s*(.+?)(?:\n|$)", re.IGNORECASE | re.MULTILINE)
_SALARY_LINE_RE = re.compile(
    r"(?:Annual Salary Expectation|Annual Salary)[:\s,]*([\d,]+)\s*(?:EUR|eur)?",
    re.IGNORECASE,
)
_COMBINED_BUDGET_RE = re.compile(
    r"(?:Maximum combined annual salary|combined annual salary)[^\d]*([\d,]+)\s*EUR",
    re.IGNORECASE,
)
_MAX_SINGLE_BUDGET_RE = re.compile(
    r"Maximum standard annual salary[^\d]*([\d,]+)\s*EUR",
    re.IGNORECASE,
)
_SEASON_GOAL_RE = re.compile(
    r"Season Goal:\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)
_FIXTURE_CONGESTION_RE = re.compile(
    r"(\d+)\s+matches in\s+(\d+)\s+days",
    re.IGNORECASE,
)
_VISION_RE = re.compile(r"Vision:\s*(\d+)", re.IGNORECASE)
_CREATIVITY_RE = re.compile(r"Creativity:\s*(\d+)", re.IGNORECASE)
_KEY_PASSING_RE = re.compile(r"Key Passing:\s*(\d+)", re.IGNORECASE)
_AVAILABILITY_UPDATE_RE = re.compile(
    r"Availability:\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)


def parse_baseline_file_content(text: str, filename: str) -> dict[str, Any]:
    """Extract structured club facts from a baseline source file."""
    facts: dict[str, Any] = {"source_file": Path(filename).name}
    lower_name = filename.lower()

    if "club_profile" in lower_name:
        goal = _SEASON_GOAL_RE.search(text)
        if goal:
            facts["season_goal"] = goal.group(1).strip()
        if "top four" in text.lower():
            facts["season_goal_short"] = "finish in the top four"

    if "transfer_budget" in lower_name:
        combined = _COMBINED_BUDGET_RE.search(text)
        if combined:
            facts["combined_budget_eur"] = _parse_int(combined.group(1))
        single = _MAX_SINGLE_BUDGET_RE.search(text)
        if single:
            facts["max_standard_salary_eur"] = _parse_int(single.group(1))
        if "70,000 EUR" in text or "70000" in text.replace(",", ""):
            facts["emergency_max_salary_eur"] = 70000

    if "fixture_congestion" in lower_name:
        match = _FIXTURE_CONGESTION_RE.search(text)
        if match:
            facts["fixture_congestion_matches"] = int(match.group(1))
            facts["fixture_congestion_days"] = int(match.group(2))
        elif "five matches in eighteen days" in text.lower():
            facts["fixture_congestion_matches"] = 5
            facts["fixture_congestion_days"] = 18

    if "squad_depth" in lower_name and "position" in text.lower():
        urgent: list[str] = []
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            priority = (row.get("priority") or "").strip().lower()
            position = (row.get("position") or "").strip()
            if priority == "high" and position:
                urgent.append(position)
        if urgent:
            facts["urgent_positions"] = urgent

    if "winter_window_priorities" in lower_name:
        priorities: list[str] = []
        if "right back" in text.lower():
            priorities.append("Right Back")
        if "attacking midfielder" in text.lower() or "below the striker" in text.lower():
            priorities.append("Attacking Midfielder")
        if "forward" in text.lower() and "50,000" in text:
            priorities.append("Forward")
        if priorities:
            facts["recruitment_priorities"] = priorities

    if "coach_tactical" in lower_name or "tactical_summary" in lower_name:
        if "4-2-3-1" in text:
            facts["primary_formation"] = "4-2-3-1"
        if "right back" in text.lower():
            facts["needs_right_back"] = True
        if "attacking midfielder" in text.lower() or "below the striker" in text.lower():
            facts["needs_attacking_midfielder"] = True

    if "winter_window_overview" in lower_name:
        combined = _COMBINED_BUDGET_RE.search(text) or re.search(
            r"([\d,]+)\s*EUR", text
        )
        if combined:
            facts["combined_budget_eur"] = _parse_int(combined.group(1))
        if "top four" in text.lower():
            facts["season_goal_short"] = "finish in the top four"
        if "right back" in text.lower():
            facts["needs_right_back"] = True

    return facts


def parse_candidate_update_content(text: str, filename: str) -> dict[str, Any]:
    """Parse availability update documents."""
    facts: dict[str, Any] = {"source_file": Path(filename).name, "is_update": True}
    name = _NAME_LINE_RE.search(text)
    if name:
        facts["full_name"] = name.group(1).strip()
    avail = _AVAILABILITY_UPDATE_RE.search(text)
    if avail:
        facts["availability"] = avail.group(1).strip()
    return facts


def parse_demo_candidate_content(text: str, filename: str) -> dict[str, Any]:
    """Parse demo candidate CV content into registry-friendly facts."""
    if "availability_update" in filename.lower() or "candidate update" in text.lower()[:80]:
        update = parse_candidate_update_content(text, filename)
        if update.get("full_name"):
            return update
    parsed = _parse_facts_from_text(text)
    if not parsed.get("full_name"):
        name = _NAME_LINE_RE.search(text)
        if name:
            parsed["full_name"] = name.group(1).strip()
    if not parsed.get("annual_salary_eur"):
        salary = _SALARY_LINE_RE.search(text)
        if salary:
            parsed["annual_salary_eur"] = _parse_int(salary.group(1))
    if "annual_salary_eur" not in parsed and "," in text.splitlines()[0].lower():
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            name = (row.get("name") or row.get("Name") or "").strip()
            if name:
                parsed["full_name"] = name
            pos = (row.get("position") or "").strip()
            if pos:
                parsed["position"] = pos
            sal = row.get("annual_salary_eur") or row.get("annual salary eur")
            if sal:
                parsed["annual_salary_eur"] = _parse_int(str(sal))
            reloc = row.get("relocation_willingness") or row.get("relocation willingness")
            if reloc:
                parsed["relocation_north"] = str(reloc).upper()
            avail = row.get("availability")
            if avail:
                parsed["availability"] = str(avail).strip()
            foot = row.get("preferred_foot") or row.get("preferred foot")
            if foot:
                parsed["preferred_foot"] = str(foot).strip().capitalize()
            for attr, key in (("vision", "vision"), ("creativity", "creativity"), ("key_passing", "key_passing")):
                val = row.get(attr)
                if val:
                    parsed[key] = _parse_int(str(val))
            break
    for attr, pattern in (
        ("vision", _VISION_RE),
        ("creativity", _CREATIVITY_RE),
        ("key_passing", _KEY_PASSING_RE),
    ):
        if attr not in parsed:
            match = pattern.search(text)
            if match:
                parsed[attr] = int(match.group(1))
    return parsed


_POSITION_LABEL_HE = {
    "Right Back": "מגן ימני",
    "Attacking Midfielder": "קשר התקפי",
    "Forward": "חלוץ",
}

_BASELINE_INTENT_SOURCES = {
    "season_goal": ["club_profile.txt", "winter_window_overview.pdf"],
    "urgent_positions": ["squad_depth_chart.csv", "winter_window_priorities.txt"],
    "immediate_availability": ["fixture_congestion_note.txt", "upcoming_fixtures.csv"],
    "transfer_budget": ["transfer_budget.txt", "winter_window_overview.pdf"],
}


def classify_baseline_question_intent(question: str) -> str | None:
    """Reusable baseline-only intent labels (English + Hebrew synonyms)."""
    q = question or ""
    ql = q.lower()
    he = _HEBREW_RE.search(q) is not None

    if any(p in ql for p in ("main goal", "season goal")) or "מטרה מרכזית" in q:
        return "season_goal"

    urgent_en = any(p in ql for p in ("urgently need", "need reinforcement", "urgent position"))
    urgent_he = he and any(
        marker in q
        for marker in (
            "חיזוק דחוף",
            "לחזק בדחיפות",
            "צריך לחזק",
            "עמדות דחופות",
            "דחופות לחיזוק",
            "דורשות חיזוק",
            "דורש חיזוק",
            "צריכה חיזוק",
        )
    ) and any(token in q for token in ("עמדות", "עמדה", "מיקומים", "מיקום"))
    if urgent_en or urgent_he:
        return "urgent_positions"

    avail_en = "immediate availability" in ql or "why is immediate availability" in ql
    avail_he = he and any(
        marker in q
        for marker in (
            "זמינות מיידית",
            "זמין מיד",
            "זמין מיידית",
            "להצטרף מיד",
            "יכול להצטרף",
            "מדוע זמינות",
            "למה זמינות",
            "למה חשוב שהשחקן",
            "למה צריך שחקן",
        )
    )
    if avail_en or avail_he:
        return "immediate_availability"

    budget_en = any(p in ql for p in ("transfer budget", "combined annual salary budget", "maximum combined"))
    budget_he = he and any(marker in q for marker in ("תקציב השכר", "תקציב כולל", "תקציב להחתמות"))
    if budget_en or budget_he:
        return "transfer_budget"

    return None


def baseline_document_names_for_intent(intent: str | None) -> list[str]:
    if not intent:
        return []
    return list(_BASELINE_INTENT_SOURCES.get(intent, []))


def is_baseline_club_question(question: str) -> bool:
    return classify_baseline_question_intent(question) is not None


def is_baseline_only_question(question: str) -> bool:
    """Questions answerable from baseline without session candidate uploads."""
    if is_baseline_club_question(question):
        return True
    q = (question or "").lower()
    if "scoutmatch fc" in q and "goal" in q:
        return True
    return False


def _budget_combo_player_names(question: str) -> tuple[bool, bool]:
    q = question or ""
    ql = q.lower()
    ron = "ron ben ari" in ql or "רון בן ארי" in q or "רון" in q
    tal = "tal raz" in ql or "טל רז" in q or "טל" in q
    return ron, tal


def is_budget_combination_question(question: str) -> bool:
    q = (question or "").lower()
    text = question or ""
    if "afford both" in q or "can the club afford" in q:
        return True
    ron, tal = _budget_combo_player_names(text)
    if not (ron and tal):
        return False
    if "afford" in q or "budget" in q:
        return True
    combo_markers_he = (
        "יכול להרשות",
        "יכולה להרשות",
        "התקציב מספיק",
        "אפשר להחתים",
        "אפשר לצרף",
        "במסגרת התקציב",
        "גם את",
        "וגם",
    )
    if any(marker in text for marker in combo_markers_he):
        return True
    if "האם" in text and ("תקציב" in text or "שכר" in text):
        return True
    return False


def is_below_striker_recommendation_question(question: str) -> bool:
    q = (question or "").lower()
    patterns = (
        "below the striker",
        "play below the striker",
        "second striker",
        "מתחת לחלוץ",
        "לשחק מתחת לחלוץ",
    )
    return any(p in q or p in (question or "") for p in patterns)


def is_immediate_right_back_question(question: str) -> bool:
    q = (question or "").lower()
    patterns = (
        "best immediate option for right back",
        "immediate option for right back",
        "best right back immediately",
        "immediate right back",
        "מגן ימני מיידי",
        "אפשרות מיידית למגן ימני",
    )
    return any(p in q or p in (question or "") for p in patterns)


def is_candidate_relocation_filter_question(question: str) -> bool:
    q = (question or "").lower()
    if "willing to relocate" in q or "candidates are willing" in q:
        return True
    if "מוכן לרילוקיישן" in (question or "") or "מוכנים לרילוקיישן" in (question or ""):
        return True
    return False


def is_immediate_right_backs_filter_question(question: str) -> bool:
    q = (question or "").lower()
    if "right backs are available immediately" in q:
        return True
    if "מגנים ימניים זמינים מיידית" in (question or ""):
        return True
    return False


def build_baseline_club_answer(question: str, club_facts: dict[str, Any]) -> str | None:
    he = _HEBREW_RE.search(question or "") is not None
    intent = classify_baseline_question_intent(question)

    if intent == "season_goal":
        goal = club_facts.get("season_goal_short") or club_facts.get("season_goal") or "finish in the top four"
        if he:
            return f"המטרה המרכזית של הקבוצה העונה היא {goal}."
        return f"The club's main goal this season is to {goal}."

    if intent == "urgent_positions":
        positions = club_facts.get("urgent_positions") or club_facts.get("recruitment_priorities") or [
            "Right Back", "Attacking Midfielder", "Forward"
        ]
        if he:
            lines = "\n".join(
                f"- {_POSITION_LABEL_HE.get(pos, pos)}" for pos in positions
            )
            return f"העמדות שדורשות חיזוק דחוף:\n{lines}"
        lines = "\n".join(f"- {pos}" for pos in positions)
        return f"Positions that urgently need reinforcement:\n{lines}"

    if intent == "immediate_availability":
        matches = club_facts.get("fixture_congestion_matches", 5)
        days = club_facts.get("fixture_congestion_days", 18)
        if he:
            return (
                f"זמינות מיידית חשובה כי ל-ScoutMatch FC יש {matches} משחקים ב-{days} יום. "
                "חיזוק מיידי שימושי במהלך לוח הזמנים הצפוף, והקבוצה צריכה שחקנים שיכולים להצטרף לאימונים מיד."
            )
        return (
            f"Immediate availability is important because ScoutMatch FC has {matches} matches "
            f"in {days} days. Immediate reinforcement is useful during the congested schedule, "
            "and the club needs players who can join training immediately."
        )

    if intent == "transfer_budget":
        total = club_facts.get("combined_budget_eur", 100000)
        formatted = _format_eur(int(total))
        if he:
            return f"תקציב השכר הכולל להחתמות חדשות הוא {formatted}."
        return f"The maximum combined annual salary budget for new signings is {formatted}."

    return None


def build_budget_combination_answer(
    question: str,
    player_facts: list[dict[str, Any]],
    club_facts: dict[str, Any],
) -> str | None:
    if not is_budget_combination_question(question):
        return None
    he = _HEBREW_RE.search(question or "") is not None
    by_name = {(p.get("full_name") or "").lower(): p for p in player_facts if p.get("full_name")}
    ron = by_name.get("ron ben ari")
    tal = by_name.get("tal raz")
    if not ron or not tal:
        return None
    ron_sal = int(ron.get("annual_salary_eur") or 0)
    tal_sal = int(tal.get("annual_salary_eur") or 0)
    total = ron_sal + tal_sal
    budget = int(club_facts.get("combined_budget_eur") or 100000)
    remaining = budget - total
    if total > budget:
        if he:
            return (
                f"לא, השילוב ({_format_eur(ron_sal)} + {_format_eur(tal_sal)} = {_format_eur(total)}) "
                f"עולה על תקציב השכר הכולל ({_format_eur(budget)})."
            )
        return (
            f"No, the combined salaries ({_format_eur(ron_sal)} + {_format_eur(tal_sal)} = "
            f"{_format_eur(total)}) exceed the combined budget ({_format_eur(budget)})."
        )
    if he:
        return (
            f"כן, הקבוצה יכולה להרשות לעצמה להחתים את Ron Ben Ari ואת Tal Raz. "
            f"{_format_eur(ron_sal)} + {_format_eur(tal_sal)} = {_format_eur(total)}; "
            f"תקציב כולל = {_format_eur(budget)}; נותר = {_format_eur(remaining)}."
        )
    return (
        f"Yes, the club can afford both Ron Ben Ari and Tal Raz. "
        f"{_format_eur(ron_sal)} + {_format_eur(tal_sal)} = {_format_eur(total)}; "
        f"combined budget = {_format_eur(budget)}; remaining = {_format_eur(remaining)}."
    )


def build_below_striker_recommendation_answer(
    question: str,
    player_facts: list[dict[str, Any]],
    club_facts: dict[str, Any],
) -> str | None:
    if not is_below_striker_recommendation_question(question):
        return None
    he = _HEBREW_RE.search(question or "") is not None
    candidates = []
    for player in player_facts:
        pos = (player.get("position") or "").lower()
        if "attacking midfielder" in pos or "second striker" in pos:
            candidates.append(player)
    if not candidates:
        return None

    def score(p: dict) -> tuple[int, int]:
        vision = int(p.get("vision") or 0)
        creativity = int(p.get("creativity") or 0)
        key_pass = int(p.get("key_passing") or 0)
        immediate = 1 if "immediate" in str(p.get("availability") or "").lower() else 0
        return (vision + creativity + key_pass, immediate)

    best = max(candidates, key=score)
    name = best.get("full_name") or "Unknown"
    salary = best.get("annual_salary_eur")
    sal_text = _format_eur(int(salary)) if salary else "unknown"
    if he:
        return (
            f"המועמד המתאים ביותר לשחק מתחת לחלוץ הוא {name}. "
            f"תפקיד: {best.get('position')}; זמינות: {best.get('availability')}; "
            f"שכר: {sal_text}; Vision: {best.get('vision')}; Creativity: {best.get('creativity')}; "
            f"Key Passing: {best.get('key_passing')}."
        )
    return (
        f"The best fit to play below the striker is {name}. "
        f"Position: {best.get('position')}; availability: {best.get('availability')}; "
        f"salary: {sal_text}; vision: {best.get('vision')}; creativity: {best.get('creativity')}; "
        f"key passing: {best.get('key_passing')}. Tactical fit aligns with the club's need for "
        "creative depth below the striker within budget."
    )


def build_immediate_right_back_answer(
    question: str,
    player_facts: list[dict[str, Any]],
) -> str | None:
    if not is_immediate_right_back_question(question):
        return None
    he = _HEBREW_RE.search(question or "") is not None
    right_backs = [
        p for p in player_facts
        if "right back" in (p.get("position") or "").lower()
    ]
    if not right_backs:
        return None

    def immediate_rank(p: dict) -> tuple[int, int]:
        avail = str(p.get("availability") or "").lower()
        is_immediate = 1 if "immediate" in avail and "march" not in avail and "2026" not in avail.replace("immediate", "") else 0
        if "march" in avail or "cannot join" in str(p.get("update_reason") or "").lower():
            is_immediate = 0
        salary = int(p.get("annual_salary_eur") or 999999)
        return (is_immediate, -salary)

    best = max(right_backs, key=immediate_rank)
    name = best.get("full_name") or "Unknown"
    avail = best.get("availability") or "unknown"
    if he:
        return (
            f"האפשרות המיידית הטובה ביותר למגן ימני היא {name} "
            f"(זמינות: {avail})."
        )
    return (
        f"The best immediate option for right back is {name} "
        f"(availability: {avail})."
    )


def build_candidate_relocation_filter_answer(
    question: str,
    player_facts: list[dict[str, Any]],
) -> str | None:
    if not is_candidate_relocation_filter_question(question):
        return None
    he = _HEBREW_RE.search(question or "") is not None
    willing = [
        p for p in player_facts
        if str(p.get("relocation_north") or "").upper() == "YES" and p.get("full_name")
    ]
    if not willing:
        return None
    lines = "\n".join(f"- {p['full_name']}" for p in willing)
    if he:
        return f"מועמדים שמוכנים לרילוקיישן:\n{lines}"
    return f"Candidates willing to relocate:\n{lines}"


def build_immediate_right_backs_filter_answer(
    question: str,
    player_facts: list[dict[str, Any]],
) -> str | None:
    if not is_immediate_right_backs_filter_question(question):
        return None
    he = _HEBREW_RE.search(question or "") is not None
    matches = [
        p for p in player_facts
        if "right back" in (p.get("position") or "").lower()
        and "immediate" in str(p.get("availability") or "").lower()
        and "march" not in str(p.get("availability") or "").lower()
    ]
    if not matches:
        return None
    lines = "\n".join(f"- {p['full_name']}" for p in matches)
    if he:
        return f"מגנים ימניים זמינים מיידית:\n{lines}"
    return f"Right backs available immediately:\n{lines}"


def build_baseline_demo_answer(
    question: str,
    player_facts: list[dict[str, Any]],
    club_facts: dict[str, Any],
) -> str | None:
    """Route baseline + demo deterministic answers."""
    for builder in (
        lambda: build_baseline_club_answer(question, club_facts),
        lambda: build_budget_combination_answer(question, player_facts, club_facts),
        lambda: build_below_striker_recommendation_answer(question, player_facts, club_facts),
        lambda: build_immediate_right_back_answer(question, player_facts),
        lambda: build_candidate_relocation_filter_answer(question, player_facts),
        lambda: build_immediate_right_backs_filter_answer(question, player_facts),
    ):
        answer = builder()
        if answer:
            return answer
    return None


def source_scope_label(s3_key: str | None, display_name: str | None = None) -> str:
    key = (s3_key or display_name or "").lower()
    if "/baseline/" in key or key.startswith("baseline/"):
        return "Club Knowledge"
    return "Uploaded Candidate Document"
