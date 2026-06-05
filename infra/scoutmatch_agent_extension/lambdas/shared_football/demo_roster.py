"""Safe demo roster loading and idempotent DynamoDB seeding."""

from __future__ import annotations

import json
from pathlib import Path

from operations_store import get_item, put_item
from validation import normalize_name

DEMO_ROSTER_ENTITY_KEY = "demo_roster#433"
DEMO_RECORD_SCOPE = "DEMO"
BUDGET_HELPER_LAMBDA = "ScoutMatchBudgetImpactAvidan"


def _roster_file_path() -> Path | None:
    parts = Path(__file__).resolve().parents
    if len(parts) < 4:
        return None
    return parts[3] / "demo_data" / "scoutmatch_demo_roster.json"


_EMBEDDED_DEMO_ROSTER: dict = {
    "record_scope": "DEMO",
    "roster_id": "scoutmatch-demo-433",
    "formation": "4-3-3",
    "players": [
        {"name": "Avi Cohen", "position": "GK"},
        {"name": "Daniel Levy", "position": "RB"},
        {"name": "Michael Ross", "position": "CB"},
        {"name": "Yossi Bar", "position": "CB"},
        {"name": "Tal Amar", "position": "LB"},
        {"name": "Noam Sharon", "position": "CM"},
        {"name": "Ido Katz", "position": "CM"},
        {"name": "Eran Blum", "position": "CM"},
        {"name": "Lior Dan", "position": "RW"},
        {"name": "Amit Peretz", "position": "ST"},
        {"name": "Guy Navon", "position": "LW"},
    ],
    "demo_right_back_candidate": {"name": "Ron Ben Ari", "position": "RB"},
}


def load_demo_roster_from_file() -> dict:
    path = _roster_file_path()
    if path is not None and path.is_file():
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    return dict(_EMBEDDED_DEMO_ROSTER)


def build_demo_starting_xi(*, ron_at_right_back: bool = True) -> list[dict]:
    """Return exactly 11 own-team starters for the sanitized 4-3-3 demo."""
    record = get_item(DEMO_ROSTER_ENTITY_KEY)
    players = list((record or {}).get("players") or [])
    if len(players) != 11:
        record = load_demo_roster_from_file()
        players = list(record.get("players") or [])
    if len(players) != 11:
        record = dict(_EMBEDDED_DEMO_ROSTER)
        players = list(record.get("players") or [])
    if len(players) != 11:
        raise ValueError("Demo roster must contain exactly 11 players.")
    if ron_at_right_back:
        candidate = (record.get("demo_right_back_candidate") or {}).get("name", "Ron Ben Ari")
        players = [p for p in players if normalize_name(p.get("name", "")) != "daniel levy"]
        players.append({"name": candidate, "position": "RB", "role_slot": "right-back"})
    return [{"name": p["name"], "position": p["position"].upper()} for p in players[:11]]


def demo_starting_xi_string(*, ron_at_right_back: bool = True) -> str:
    return ";".join(f"{p['name']}:{p['position']}" for p in build_demo_starting_xi(ron_at_right_back=ron_at_right_back))


def is_demo_lineup_request(params: dict) -> bool:
    truthy = {"1", "true", "yes", "demo"}
    if params.get("demo_lineup") is True:
        return True
    if str(params.get("demo_lineup", "")).strip().lower() in truthy:
        return True
    if (params.get("lineup_mode") or "").strip().lower() == "demo":
        return True
    xi = (params.get("starting_xi") or "").strip().lower()
    if xi in {"demo", "demo_lineup", "use_demo_roster", "demo roster"}:
        return True
    notes = (params.get("coach_notes") or params.get("lineup_notes") or "").strip().lower()
    return "demo lineup" in notes or "demo 4-3-3" in notes


def seed_demo_roster_idempotent(*, apply: bool = False) -> dict:
    """
    Seed demo roster into ScoutMatchFootballOperationsAvidan.

    Skips when a non-demo record already occupies the key.
    Re-seeds only when missing or existing record_scope is DEMO.
    """
    existing = get_item(DEMO_ROSTER_ENTITY_KEY)
    if existing and existing.get("record_scope") not in {None, "", DEMO_RECORD_SCOPE}:
        return {"status": "SKIPPED", "reason": "non_demo_record_present", "entity_key": DEMO_ROSTER_ENTITY_KEY}
    if existing and existing.get("record_scope") == DEMO_RECORD_SCOPE:
        return {"status": "ALREADY_SEEDED", "entity_key": DEMO_ROSTER_ENTITY_KEY}

    payload = load_demo_roster_from_file()
    if payload.get("record_scope") != DEMO_RECORD_SCOPE:
        return {"status": "REJECTED", "reason": "invalid_record_scope"}

    if not apply:
        return {"status": "PLANNED", "entity_key": DEMO_ROSTER_ENTITY_KEY, "record_scope": DEMO_RECORD_SCOPE}

    put_item(
        entity_key=DEMO_ROSTER_ENTITY_KEY,
        item_type="DEMO_ROSTER",
        payload={
            **payload,
            "record_scope": DEMO_RECORD_SCOPE,
            "entity_key": DEMO_ROSTER_ENTITY_KEY,
        },
    )
    return {"status": "SEEDED", "entity_key": DEMO_ROSTER_ENTITY_KEY, "record_scope": DEMO_RECORD_SCOPE}
