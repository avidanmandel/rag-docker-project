"""Deterministic tactical planning from coach context and documented rules."""

from __future__ import annotations

import re
import uuid

from operations_store import put_item


def _is_coach_brief(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return lowered.startswith("coach brief:") or "coach brief" in lowered[:40]


def _signals(squad_context: str) -> dict[str, bool]:
    text = squad_context.lower()
    return {
        "goalkeeper_injured": bool(
            re.search(
                r"goalkeeper|goal keeper|starting gk|reserve goalkeeper",
                text,
            )
            and re.search(
                r"injur|unavailable|miss(?:ed|ing)?|out|suspension|illness|fitness concern|"
                r"will miss|next\s+\d+\s+match",
                text,
            )
        ),
        "left_back_unavailable": bool(
            re.search(r"left[- ]?back.{0,40}(unavailable|injured|missing|out)", text)
            or re.search(r"(unavailable|injured|missing|out).{0,40}left[- ]?back", text)
        ),
        "weak_right_back": bool(
            re.search(r"right[- ]?back.{0,60}(weak|no strong|not.{0,20}strong|within the budget)", text)
            or re.search(r"no.{0,20}strong right[- ]?back", text)
        ),
        "striker_alone": bool(
            re.search(r"striker.{0,40}(alone|aggressive|operate alone|play alone)", text)
            or re.search(r"aggressive.{0,20}striker", text)
        ),
        "needs_width": "width" in text or "attacking width" in text,
        "needs_stability": "defensive stability" in text or "compact" in text,
    }


def plan_match_tactics(
    *,
    opponent: str,
    squad_context: str,
    available_budget_eur: int | None = None,
    preferred_style: str = "",
    formation_options: str = "",
) -> dict:
    opponent = (opponent or "").strip()[:120]
    squad_context = (squad_context or "").strip()[:2000]
    coach_brief = _is_coach_brief(squad_context)
    if coach_brief:
        squad_context = re.sub(r"^\s*coach\s+brief\s*:\s*", "", squad_context, flags=re.I).strip()
    if not squad_context:
        return {"status": "NEEDS_CLARIFICATION", "message": "squad_context is required"}
    if not opponent:
        opponent = "next fixture" if coach_brief else ""
    if not opponent:
        return {"status": "NEEDS_CLARIFICATION", "message": "opponent is required"}

    signals = _signals(squad_context)
    planning_context_id = f"ctx-{uuid.uuid4().hex[:10]}"

    if signals["goalkeeper_injured"]:
        primary = "5-4-1"
        style = "compact defensive structure with controlled build-up"
        reasoning = [
            "Urgent squad need detected: Goalkeeper.",
            "Priority: find a replacement goalkeeper within the available budget.",
            "Temporary recommendation for the head coach: use the reserve goalkeeper and play "
            "with a more compact defensive structure.",
            "Avoid an overly aggressive defensive line until a replacement is approved.",
        ]
        alternative = "4-4-2"
        tradeoff = "More midfield cover but less natural compactness in front of goal."
        not_recommended = []
    elif signals["weak_right_back"] and signals["striker_alone"]:
        primary = "5-4-1"
        style = "compact defensive structure with counterattacks"
        reasoning = [
            "The squad currently lacks reliable full-back coverage within the stated budget.",
            "The striker can operate alone in a compact structure.",
            "A 5-4-1 reduces exposure in wide defensive areas.",
        ]
        alternative = "3-4-3"
        tradeoff = "More attacking width but greater defensive risk without reliable full-backs."
        not_recommended = [
            {
                "formation": "4-3-3",
                "reason": "Requires reliable full-backs, which are currently unavailable or weak.",
            }
        ]
    elif signals["needs_width"] and not signals["weak_right_back"]:
        primary = "4-3-3"
        style = "balanced width with controlled pressing"
        reasoning = [
            "Documented 4-3-3 guidance supports attacking width when full-back coverage is reliable.",
        ]
        alternative = "3-4-3"
        tradeoff = "Adds an extra center-back but needs strong wide midfield coverage."
        not_recommended = []
    else:
        primary = "4-3-3"
        style = "balanced possession with structured width"
        reasoning = [
            "Default documented recommendation when full-back risk is not the dominant constraint.",
        ]
        alternative = "5-4-1"
        tradeoff = "More defensive stability but less natural attacking width."
        not_recommended = []

    if signals["left_back_unavailable"] and primary == "4-3-3":
        not_recommended.append(
            {
                "formation": "4-3-3",
                "reason": "Left-back is unavailable and 4-3-3 depends on reliable full-back coverage.",
            }
        )
        primary = "5-4-1"
        style = "compact defensive structure with counterattacks"
        reasoning = [
            "Left-back is unavailable.",
            "A compact shape limits exposure on the weak flank.",
        ]

    record = put_item(
        entity_key="squad_context#current",
        item_type="SQUAD_CONTEXT",
        payload={
            "planning_context_id": planning_context_id,
            "opponent": opponent,
            "preferred_formation": primary,
            "priority_positions": "RB" if signals["weak_right_back"] else "",
            "strong_positions": "attack" if signals["striker_alone"] else "",
            "available_budget_eur": int(available_budget_eur or 0),
            "coach_notes": squad_context[:500],
            "preferred_style": preferred_style[:200],
            "formation_options": formation_options[:200],
        },
    )
    put_item(
        entity_key=f"tactical_plan#{planning_context_id}",
        item_type="TACTICAL_PLAN",
        payload={
            "planning_context_id": planning_context_id,
            "opponent": opponent,
            "recommended_formation": primary,
            "recommended_style": style,
            "reasoning_summary": reasoning,
            "alternative_formation": alternative,
            "alternative_tradeoff": tradeoff,
            "not_recommended": not_recommended,
            "evidence_note": "Computed from coach-provided updates and documented ScoutMatch tactical rules.",
        },
    )
    response = {
        "status": "TACTICAL_PLAN_UPDATED",
        "recommended_formation": primary,
        "recommended_style": style,
        "reasoning_summary": reasoning,
        "alternative_formation": alternative,
        "alternative_tradeoff": tradeoff,
        "not_recommended": not_recommended,
        "planning_context_id": planning_context_id,
        "context": record,
        "read_only": True,
    }
    if signals["goalkeeper_injured"]:
        response["urgent_squad_need"] = "Goalkeeper"
        response["priority_recommendation"] = (
            "Find a replacement goalkeeper within the available budget."
        )
        response["temporary_head_coach_recommendation"] = (
            "Use the reserve goalkeeper and play with a more compact defensive structure."
        )
    if coach_brief:
        response["coach_brief_handled"] = True
    return response
