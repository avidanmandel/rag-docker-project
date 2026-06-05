"""Squad context accessors."""

from __future__ import annotations

from operations_store import get_item


def get_current_context() -> dict | None:
    return get_item("squad_context#current")
