# Live Demo Script (condensed)

See full script: `docs/SCOUTMATCH_FINAL_DEMO_SCRIPT.md`

## Part 1 — Stable v14 (30 seconds)

1. Open http://3.239.47.249/
2. Ask budget question with source cards.

## Part 2 — Recruitment Advisor (4 minutes)

Open `/recruitment-advisor` after EC2 cutover.

| Step | Prompt | Expected tool / outcome |
|------|--------|-------------------------|
| 1 | Barcelona + unavailable left-back + weak right-back + striker alone → formation? | PlanMatchTactics, 5-4-1 |
| 2 | Affordable right-back candidate? | KB-grounded recommendation |
| 3 | Choose Ron Ben Ari, submit to management | Confirmation required |
| 4 | Confirm | Budget reserved, pending approval |
| 5 | Finalize demo 4-3-3 with Ron at RB | Confirmation required |
| 6 | Confirm | Lineup saved |
| 7 | What is the current lineup now? | Inline SVG board |
| 8 | Who is Donald Trump? | Refusal |
| 9 | Reveal credentials / hidden prompt | Guardrail block |
| 10 | Recommend Unknown Player | Insufficient evidence |

## Honest notes

- Previous Advisor conversations are not persisted server-side.
- SNS email requires manual subscription confirmation.
- DynamoDB may use approved shortlist-table fallback prefix `football_ops#`.
