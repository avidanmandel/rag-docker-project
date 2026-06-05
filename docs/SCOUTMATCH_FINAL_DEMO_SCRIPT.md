# ScoutMatch Final Demo Script (5–7 minutes)

Use production v14 for grounded RAG, then local Recruitment Advisor for dynamic operations (after approved `--apply`).

## Prerequisites

- Production URL: http://3.239.47.249/
- Local Advisor: enable `SCOUTMATCH_AGENT_EXTENSION_ENABLED=true` in `.env.agent` (never commit)
- Same browser; note session id reuse in Advisor UI

## Script

| Step | Time | Action | Expected result |
|------|------|--------|-----------------|
| 1 | 0:30 | Open public ScoutMatch UI | Homepage loads; football branding visible |
| 2 | 0:45 | Ask: *What is the maximum combined annual salary budget for new signings?* | Grounded answer **100,000 EUR** with source cards |
| 3 | 1:00 | Point to source cards | Documents from Knowledge Base; no invented numbers |
| 4 | 1:15 | Open `/recruitment-advisor` (local) | Isolated Advisor UI; v14 chat unchanged |
| 5 | 1:45 | Sporting director: *Our next important match is against Barcelona. We want 4-3-3. Attack is strong, right-back needs reinforcement. We have 55000 EUR available. Who should we prioritize?* | Context saved; RAG-based Ron vs Tal comparison |
| 6 | 2:30 | *Compare Ron Ben Ari with the cheaper option for this match.* | Opponent and budget remembered in same session |
| 7 | 3:00 | *I choose Ron Ben Ari because he is the more aggressive option. Submit the selection to management.* | `SubmitPlayerSelectionToManagement`; confirmation requested |
| 8 | 3:15 | *Deny* (optional negative test) | No DynamoDB reservation |
| 9 | 3:30 | Repeat submit → *Confirm* | 43,000 EUR reserved; remaining **12,000 EUR**; SNS published; **PENDING_MANAGEMENT_APPROVAL** |
| 10 | 4:00 | Show DynamoDB reservation + SNS topic publish (console) | Sanitized evidence only |
| 11 | 4:30 | *Finalize the updated 4-3-3 lineup with Ron Ben Ari at right-back.* → *Confirm* | 11 starters saved |
| 12 | 5:00 | *What is the current lineup now?* | `GenerateCurrentLineupBoard`; inline SVG in chat |
| 13 | 5:30 | Open larger board; show pending-approval badge on Ron | Own team only; opponent in title only |
| 14 | 6:00 | Ask: *Who is Donald Trump?* or credentials probe | Refusal / guardrail |
| 15 | 6:30 | Architecture closing | v14 = KB retrieve; Advisor = Agent + KB + 4 Tools + DynamoDB state |

## Honest limitations to mention

- **Previous Advisor conversations** are not persisted server-side; only the current thread and `sessionStorage` session id are kept.
- **Dynamic Advisor** is local-only unless explicitly deployed; production EC2 remains v14.
- **Management approval** is never invented; status stays pending until recorded in DynamoDB.
