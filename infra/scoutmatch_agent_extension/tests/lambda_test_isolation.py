"""Reload football_operations vs shared_football modules without sys.path collisions."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EXT = Path(__file__).resolve().parents[1]
OPS = EXT / "lambdas" / "football_operations"
COMMON = EXT / "lambdas" / "common"
SHARED = EXT / "lambdas" / "shared_football"

CONFLICTING_MODULES = (
    "availability",
    "budget_ledger",
    "budget_rules",
    "critical_decision",
    "demo_roster",
    "feature_flags",
    "google_calendar_adapter",
    "ics_calendar",
    "lineup_store",
    "lineup_svg",
    "operations_store",
    "player_selection",
    "scouting_mission",
    "season_context",
    "ses_adapter",
    "sns_notification",
    "squad_context",
    "squad_depth",
    "tactical_planner",
    "transfer_out_review",
    "validation",
    "visual_squad_board",
)

FOOTBALL_PRELOAD_ORDER = (
    "operations_store",
    "budget_ledger",
    "validation",
    "sns_notification",
    "demo_roster",
    "squad_context",
    "availability",
    "player_selection",
    "lineup_store",
    "lineup_svg",
    "squad_depth",
)

SHARED_PRELOAD_ORDER = (
    "operations_store",
    "budget_rules",
    "budget_ledger",
    "validation",
    "sns_notification",
    "demo_roster",
    "squad_context",
    "feature_flags",
    "season_context",
    "transfer_out_review",
    "scouting_mission",
    "critical_decision",
    "ics_calendar",
    "google_calendar_adapter",
    "ses_adapter",
    "player_selection",
    "lineup_store",
    "lineup_svg",
    "visual_squad_board",
    "tactical_planner",
)


def evict_conflicting_modules() -> None:
    for name in CONFLICTING_MODULES:
        sys.modules.pop(name, None)
    sys.modules.pop("football_ops_lambda", None)


def _promote_paths(*paths: str) -> list[str]:
    """Move paths to the front of sys.path; return removed entries for restoration."""
    removed: list[str] = []
    for path in reversed(paths):
        norm = str(Path(path).resolve())
        while norm in sys.path:
            sys.path.remove(norm)
            removed.append(norm)
        sys.path.insert(0, norm)
    return removed


def _load_from(root: Path, name: str, prefix: str):
    path = root / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{prefix}{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    sys.modules[name] = module
    return module


def reload_football_operations_lambda():
    """Return (lambda_module, operations_store_module) bound to football_operations."""
    evict_conflicting_modules()
    _promote_paths(str(COMMON), str(OPS))

    for name in FOOTBALL_PRELOAD_ORDER:
        _load_from(OPS, name, "football_")

    spec = importlib.util.spec_from_file_location("football_ops_lambda", OPS / "lambda_function.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    sys.modules["football_ops_lambda"] = module
    return module, sys.modules["operations_store"]


def reload_shared_football_modules() -> None:
    """Bind shared_football modules to canonical names for V2 Lambda tests."""
    evict_conflicting_modules()
    _promote_paths(str(COMMON), str(SHARED))
    for name in SHARED_PRELOAD_ORDER:
        if (SHARED / f"{name}.py").exists():
            _load_from(SHARED, name, "shared_")
