#!/usr/bin/env python3
"""Three-run reliability check for the four V2 write tools via staging HTTP API."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "evidence" / "business_workflow_v2_staging" / "four_tool_reliability.json"
BASE = os.getenv("SCOUTMATCH_V2_STAGING_URL", "http://127.0.0.1:5002").rstrip("/")
RUNS = int(os.getenv("RELIABILITY_RUNS", "3"))

TOOLS = (
    ("OpenTransferOutReviewCase", "Open a transfer-out review case for Daniel Cohen."),
    (
        "CreateAndReviewScoutingMission",
        "Create a scouting mission for Ron Ben Ari's next match and add it to my calendar.",
    ),
    (
        "SubmitCriticalDecisionAndSendEmail",
        "I choose Ron Ben Ari as our right-back candidate. Submit the recommendation for management review.",
    ),
    (
        "GenerateVisualSquadAndLineupBoard",
        "Save and show the proposed 4-3-3 lineup for head-coach review.",
    ),
)


def chat(prompt: str) -> dict:
    sess = json.loads(
        urllib.request.urlopen(
            urllib.request.Request(
                f"{BASE}/api/sessions",
                json.dumps({}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            ),
            timeout=320,
        ).read()
    )
    sid = sess["id"]
    t0 = time.time()
    out = json.loads(
        urllib.request.urlopen(
            urllib.request.Request(
                f"{BASE}/api/sessions/{sid}/messages",
                json.dumps({"content": prompt}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            ),
            timeout=320,
        ).read()
    )
    meta = out.get("agent_metadata") or {}
    pending = meta.get("pending_return_control") or {}
    return {
        "elapsed_s": round(time.time() - t0, 1),
        "pending": bool(pending.get("invocation_id")),
        "function": pending.get("function"),
        "confirmation_card": bool(meta.get("confirmation_card")),
    }


def main() -> int:
    report: dict = {"base_url": BASE, "runs_per_tool": RUNS, "tools": {}}
    all_ok = True
    for tool_name, prompt in TOOLS:
        runs = []
        for i in range(RUNS):
            result = chat(prompt)
            ok = result["pending"] and result["function"] == tool_name and result["confirmation_card"]
            result["ok"] = ok
            runs.append(result)
            all_ok = all_ok and ok
        report["tools"][tool_name] = {
            "success_count": sum(1 for row in runs if row["ok"]),
            "runs": runs,
        }
    report["status"] = "OK" if all_ok else "PARTIAL"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
