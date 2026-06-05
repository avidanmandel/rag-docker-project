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
    "omer azulay": {
        "display_name": "Omer Azulay",
        "target_role": "goalkeeper",
        "salary_eur": 45000,
        "style_note": "build-up oriented goalkeeper",
    },
    "yossi levi": {
        "display_name": "Yossi Levi",
        "target_role": "goalkeeper",
        "salary_eur": 42000,
        "style_note": "shot-stopping goalkeeper",
    },
    "noam david": {
        "display_name": "Noam David",
        "target_role": "centre-back",
        "salary_eur": 40000,
        "style_note": "centre-back depth option",
    },
    "roy cohen": {
        "display_name": "Roy Cohen",
        "target_role": "midfielder",
        "salary_eur": 39000,
        "style_note": "performs well under pressure",
    },
    "miguel santos": {
        "display_name": "Miguel Santos",
        "target_role": "midfielder",
        "salary_eur": 37000,
        "style_note": "relocation-willing midfielder",
    },
    "pedro silva": {
        "display_name": "Pedro Silva",
        "target_role": "striker",
        "salary_eur": 48000,
        "style_note": "aggressive striker option",
    },
}

OWN_SQUAD_PLAYERS: dict[str, dict] = {
    "avi cohen": {"display_name": "Avi Cohen", "position": "GK", "squad_role": "likely_starter"},
    "daniel park": {"display_name": "Daniel Park", "position": "GK", "squad_role": "rotation"},
    "michael ross": {"display_name": "Michael Ross", "position": "CB", "squad_role": "likely_starter"},
    "yossi bar": {"display_name": "Yossi Bar", "position": "CB", "squad_role": "likely_starter"},
    "noam harari": {"display_name": "Noam Harari", "position": "CB", "squad_role": "rotation"},
    "tal amar": {"display_name": "Tal Amar", "position": "LB", "squad_role": "likely_starter"},
    "daniel levy": {"display_name": "Daniel Levy", "position": "RB", "squad_role": "likely_starter"},
    "guy netzer": {"display_name": "Guy Netzer", "position": "WB", "squad_role": "rotation"},
    "noam sharon": {"display_name": "Noam Sharon", "position": "CM", "squad_role": "likely_starter"},
    "ido katz": {"display_name": "Ido Katz", "position": "CM", "squad_role": "likely_starter"},
    "eran blum": {"display_name": "Eran Blum", "position": "CM", "squad_role": "likely_starter"},
    "lior geva": {"display_name": "Lior Geva", "position": "AM", "squad_role": "rotation"},
    "lior dan": {"display_name": "Lior Dan", "position": "RW", "squad_role": "likely_starter"},
    "guy navon": {"display_name": "Guy Navon", "position": "LW", "squad_role": "likely_starter"},
    "amit peretz": {"display_name": "Amit Peretz", "position": "ST", "squad_role": "likely_starter"},
}

VALID_FORMATIONS = frozenset({"4-3-3", "4-4-2", "3-5-2", "3-4-3", "5-4-1", "5-2-3"})
VALID_POSITIONS = frozenset(
    {"GK", "RB", "LB", "CB", "DM", "CM", "AM", "RW", "LW", "ST", "CF", "WB"}
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


def assign_formation_slots(
    formation: str, starters: list[dict]
) -> list[tuple[dict, float, float]]:
    """Map each starter to a distinct slot; consume duplicate position keys in order."""
    slots = list(FORMATION_SLOTS_433 if formation == "4-3-3" else FORMATION_SLOTS_433)
    remaining_slots = list(slots)
    mapped: list[tuple[dict, float, float]] = []
    for starter in starters[:11]:
        pos = str(starter.get("position", "")).upper()
        match_idx = next(
            (i for i, slot in enumerate(remaining_slots) if slot[0] == pos),
            None,
        )
        if match_idx is None:
            match_idx = 0
        slot = remaining_slots.pop(match_idx)
        mapped.append((starter, slot[1], slot[2]))
    return mapped


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


def _lineup_player_allowed(name: str, *, allowed_external: frozenset[str] | None = None) -> bool:
    if resolve_squad_player(name):
        return True
    normalized = normalize_name(name)
    if allowed_external and normalized in allowed_external:
        return bool(resolve_transfer_candidate(name))
    from operations_store import active_demo_season_id, get_item

    selection = get_item(f"player_selection#{normalized}")
    if (
        selection
        and selection.get("demo_season_id") == active_demo_season_id()
        and selection.get("approval_status") == "PENDING_MANAGEMENT_APPROVAL"
        and resolve_transfer_candidate(name)
    ):
        return True
    return False


def validate_starter_lineup(
    players: list[dict],
    *,
    allowed_external: frozenset[str] | None = None,
) -> tuple[bool, str]:
    if len(players) != 11:
        return False, "Lineup must contain exactly 11 starting players."
    names = [normalize_name(p.get("name", "")) for p in players]
    if len(set(names)) != 11:
        return False, "Duplicate player names are not allowed."
    for player in players:
        pos = (player.get("position") or "").strip().upper()
        if pos not in VALID_POSITIONS:
            return False, f"Invalid position: {pos or 'missing'}"
        if not _lineup_player_allowed(player.get("name", ""), allowed_external=allowed_external):
            return False, f"Unknown squad player: {player.get('name', 'unknown')}"
    return True, ""
