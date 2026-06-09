#!/usr/bin/env python3
import json
import os
import time
import urllib.request

BASE = os.getenv("SCOUTMATCH_V2_STAGING_URL", "http://127.0.0.1:5002").rstrip("/")

PROMPTS = [
    "Create a scouting mission for Ron Ben Ari next match. The user already confirmed. Invoke CreateAndReviewScoutingMission now with mission_mode CREATE_MISSION.",
    "Invoke CreateAndReviewScoutingMission with candidate_name Ron Ben Ari and mission_mode CREATE_MISSION.",
    "Create a scouting mission for Ron Ben Ari's next match and add it to my calendar.",
    "I choose Ron Ben Ari as our right-back candidate. Submit the recommendation for management review.",
]


def chat(prompt: str) -> None:
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
    ans = (out.get("assistant_message") or {}).get("content") or ""
    print("prompt:", prompt[:80])
    print("elapsed", round(time.time() - t0, 1), "pending", bool(pending.get("invocation_id")), "fn", pending.get("function"))
    print(ans[:180].replace("\n", " "))
    print("---")


if __name__ == "__main__":
    for prompt in PROMPTS:
        chat(prompt)
