# ScoutMatch Final Demo Script (5–7 minutes)

**Public URL:** http://3.239.47.249/  
**UI:** Polished root page `/` only — `/recruitment-advisor` is diagnostic.  
**SNS:** Not part of this demo. DynamoDB is the source of truth for recommendations.

---

## Before you start

- Use a fresh browser tab (new conversation).
- All prompts below passed live validation on 2026-06-04.
- If Agent latency or network fails, switch to backup screenshots in `submission_evidence/final_v14/` and `submission_evidence/agent_flow_extension/`.

---

## Demo script

| Step | Time | Say / Do | Expected result |
|------|------|----------|-----------------|
| 1 | 0:20 | Open http://3.239.47.249/ | Landing page loads; opening-season storyline; quick-start cards visible |
| 2 | 0:40 | *"Before the opening match, we need to understand our squad weaknesses using the current club squad and depth analysis."* | Grounded answer; right-back and goalkeeper gaps discussed; source cards visible |
| 3 | 1:10 | *"Compare the right-back candidates within our recruitment budget. Include Ron Ben Ari and Tal Cohen."* | Both players discussed; budget considered; no invented facts |
| 4 | 1:40 | *"Our starting goalkeeper was injured during training and will miss the next three matches. Which position should we prioritize and what tactical adjustment should we propose to the head coach?"* | PlanMatchTactics runs; goalkeeper priority; tactical adjustment; no budget write |
| 5 | 2:10 | *"I choose Ron Ben Ari because he is the more aggressive right-back option. Submit the player recommendation to management."* | Confirmation card with Confirm / Deny; **no write yet** |
| 6 | 2:25 | Click **Confirm** | Clean wording: pending management approval; reserved 43,000 EUR; remaining 57,000 EUR |
| 7 | 2:50 | *"Save the proposed demo 4-3-3 lineup with Ron Ben Ari at right-back for head-coach review."* → **Confirm** | 11 players saved; pending head-coach review |
| 8 | 3:20 | *"Show me the current proposed lineup."* | Inline lineup board; formation 4-3-3; 11 players; proxy route only (no public S3 URL) |
| 9 | 3:50 | Explain closing line | Management approval and head-coach sign-off remain **outside** ScoutMatch |
| 10 | 4:10 | Optional safety (30 s each) | Off-topic refused; credential request blocked by Guardrail |

**Total:** ~4–5 minutes core flow + optional safety = **5–7 minutes**.

---

## Stable prompts (copy-paste)

```
Analyze our current squad weaknesses before the opening match. Use the current club squad and squad depth analysis.
```

```
Compare the right-back candidates within our recruitment budget. Include Ron Ben Ari and Tal Cohen.
```

```
Our starting goalkeeper was injured during training and will miss the next three matches. Which position should we prioritize and what tactical adjustment should we propose to the head coach?
```

```
I choose Ron Ben Ari because he is the more aggressive right-back option. Submit the player recommendation to management.
```

```
Save the proposed demo 4-3-3 lineup with Ron Ben Ari at right-back for head-coach review.
```

```
Show me the current proposed lineup.
```

---

## What to say after Confirm (player selection)

> Recommendation submitted for management review.  
> Status: Pending management approval.  
> Reserved budget: 43,000 EUR.  
> Remaining budget: 57,000 EUR.

Do **not** say the player was signed or that management approved the deal.

---

## Backup plan (if live demo fails)

| Failure | Backup |
|---------|--------|
| Agent timeout | Show `31_dynamic_analyst_chat.png` + `06_grounded_budget_answer_with_sources.png` |
| Confirmation card missing | Show `33_player_selection_confirmation.png` |
| Lineup board missing | Show `40_inline_lineup_board_chat.png` + `41_lineup_board_433.png` |
| Homepage issue | Show `05_public_scoutmatch_homepage.png` from `submission_evidence/final_v14/` |

---

## Honest limitations (one sentence each)

- Previous Advisor conversations are not persisted server-side.
- Dedicated DynamoDB table may use an approved fallback prefix when table create is denied.
- Management and head-coach approval are manual steps outside the application.
