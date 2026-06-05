"""Validation helpers and approved demo player catalog."""

from __future__ import annotations

import re

APPROVED_TRANSFER_CANDIDATES: dict[str, dict] = {
    "ron ben ari": {
        "display_name": "Ron Ben Ari",
        "target_role": "right-back",
        "salary_eur": 43000,
        "style_note": "aggressive overlapping right-back",
    },
    "tal cohen": {
        "display_name": "Tal Cohen",
        "target_role": "right-back",
        "salary_eur": 38000,
        "style_note": "budget-flexible right-back option",
    },
    "or david": {
        "display_name": "Or David",
        "target_role": "forward",
        "salary_eur": 55000,
        "style_note": "documented forward link-up profile",
    },
}

OWN_SQUAD_PLAYERS: dict[str, dict] = {
    "avi cohen": {"display_name": "Avi Cohen", "position": "GK"},
    "daniel levy": {"display_name": "Daniel Levy", "position": "RB"},
    "ron ben ari": {"display_name": "Ron Ben Ari", "position": "RB", "transfer_candidate": True},
    "michael ross": {"display_name": "Michael Ross", "position": "CB"},
    "yossi bar": {"display_name": "Yossi Bar", "position": "CB"},
    "tal amar": {"display_name": "Tal Amar", "position": "LB"},
    "noam sharon": {"display_name": "Noam Sharon", "position": "CM"},
    "ido katz": {"display_name": "Ido Katz", "position": "CM"},
    "eran blum": {"display_name": "Eran Blum", "position": "CM"},
    "lior dan": {"display_name": "Lior Dan", "position": "RW"},
    "guy navon": {"display_name": "Guy Navon", "position": "LW"},
    "amit peretz": {"display_name": "Amit Peretz", "position": "ST"},
    "or david": {"display_name": "Or David", "position": "ST", "transfer_candidate": True},
}

VALID_FORMATIONS = frozenset({"4-3-3", "4-4-2", "3-5-2"})
VALID_POSITIONS = frozenset(
    {"GK", "RB", "LB", "CB", "DM", "CM", "AM", "RW", "LW", "ST", "CF"}
)
FORMATION_SLOTS_433 = [
    ("GK", 0.5, 0.92),
    ("RB", 0.78, 0.72),
    ("CB", 0.62, 0.78),
    ("CB", 0.38, 0.78),
    ("LB", 0.22, 0.72),
    ("CM", 0.65, 0.52),
    ("CM", 0.5, 0.48),
    ("CM", 0.35, 0.52),
    ("RW", 0.78, 0.28),
    ("ST", 0.5, 0.18),
    ("LW", 0.22, 0.28),
]


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def slug_name(name: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", normalize_name(name)).strip("-")
    return token or "player"


def resolve_transfer_candidate(name: str) -> dict | None:
    return APPROVED_TRANSFER_CANDIDATES.get(normalize_name(name))


def resolve_squad_player(name: str) -> dict | None:
    return OWN_SQUAD_PLAYERS.get(normalize_name(name))


def validate_formation(formation: str) -> bool:
    return formation.strip() in VALID_FORMATIONS


def validate_starter_lineup(players: list[dict]) -> tuple[bool, str]:
    if len(players) != 11:
        return False, "Lineup must contain exactly 11 starting players."
    names = [normalize_name(p.get("name", "")) for p in players]
    if len(set(names)) != 11:
        return False, "Duplicate player names are not allowed."
    for player in players:
        pos = (player.get("position") or "").strip().upper()
        if pos not in VALID_POSITIONS:
            return False, f"Invalid position: {pos or 'missing'}"
        if not resolve_squad_player(player.get("name", "")):
            return False, f"Unknown squad player: {player.get('name', 'unknown')}"
    return True, ""
