#!/usr/bin/env python3
"""
PLAN ONLY — prints ordered cleanup steps. Never deletes resources.
See docs/SCOUTMATCH_AWS_CLEANUP_PLAN.md
"""

from __future__ import annotations

STEPS = [
    "1. Disable SCOUTMATCH_FLOW_EXTENSION_ENABLED in any local .env.agent (do not commit).",
    "2. Delete flow alias scoutmatch-recruitment-flow-demo-user5-avidan (after explicit approval).",
    "3. Delete flow versions for scoutmatch-recruitment-flow-user5-avidan.",
    "4. Delete flow scoutmatch-recruitment-flow-user5-avidan.",
    "5. Delete agent alias scoutmatch-recruitment-demo-user5-avidan.",
    "6. Delete agent scoutmatch-recruitment-agent-user5-avidan.",
    "7. Delete guardrail scoutmatch-guardrail-user5-avidan.",
    "8. Remove Lambda resource policies, then delete the four ScoutMatch*Avidan Lambdas.",
    "9. Delete IAM roles ScoutMatchExtension*Avidan (after detaching policies).",
    "10. Do NOT delete knowledge-base-user5, legacy demo resources, or production EC2/S3.",
]


def main() -> int:
    print("ScoutMatch extension cleanup — PLAN ONLY (no AWS calls)\n")
    for step in STEPS:
        print(step)
    print("\nNo resources were modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
