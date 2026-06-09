#!/usr/bin/env python3
import json
import os
import time
import urllib.request

BASE = os.getenv("SCOUTMATCH_V2_STAGING_URL", "http://127.0.0.1:5002").rstrip("/")
PROMPTS = [
    (
        "I choose Ron Ben Ari as our right-back candidate. "
        "Submit the recommendation for management review."
    ),
    (
        "Invoke SubmitCriticalDecisionAndSendEmail with candidate_name Ron Ben Ari, "
        "salary_eur 43000, and target_role Right-back."
    ),
]


def chat(prompt: str) -> tuple[float, bool]:
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
    pending = (out.get("agent_metadata") or {}).get("pending_return_control") or {}
    return round(time.time() - t0, 1), bool(pending.get("invocation_id"))


if __name__ == "__main__":
    runs = int(os.getenv("PROBE_RUNS", "3"))
    for prompt in PROMPTS:
        ok = 0
        print("prompt:", prompt[:70])
        for i in range(runs):
            elapsed, pending = chat(prompt)
            ok += int(pending)
            print(f"  run={i+1} elapsed={elapsed}s pending={pending}")
        print(f"  success={ok}/{runs}")
        print("---")
