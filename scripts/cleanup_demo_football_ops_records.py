#!/usr/bin/env python3
"""Manual demo cleanup — requires explicit operator confirmation."""

from __future__ import annotations

import sys

CONFIRM_PHRASE = "DELETE_DEMO_FOOTBALL_OPS_ONLY"


def main() -> int:
    print("This script is intentionally disabled by default.")
    print("It deletes only football_ops# demo PLAYER_SELECTION and BUDGET_LEDGER records.")
    print(f"To proceed, rerun with: python {__file__} {CONFIRM_PHRASE}")
    if len(sys.argv) < 2 or sys.argv[1] != CONFIRM_PHRASE:
        return 2
    print("Cleanup execution is not automated in this repository build.")
    print("Perform deletion manually in DynamoDB console using the audit criteria.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
