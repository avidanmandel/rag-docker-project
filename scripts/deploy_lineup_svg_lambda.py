#!/usr/bin/env python3
"""Update the four final Lambdas with current shared_football modules (lineup SVG fix)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "infra" / "scoutmatch_agent_extension" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from four_lambda_apply import FINAL_FOUR_LAMBDAS  # noqa: E402
from deploy_final_four_lambda import zip_final_lambda  # noqa: E402


def main() -> int:
    import boto3

    client = boto3.client("lambda", region_name="us-east-1")
    for name, spec in FINAL_FOUR_LAMBDAS.items():
        folder = spec["folder"]
        payload = zip_final_lambda(folder)
        client.update_function_code(FunctionName=name, ZipFile=payload)
        print(f"UPDATED {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
