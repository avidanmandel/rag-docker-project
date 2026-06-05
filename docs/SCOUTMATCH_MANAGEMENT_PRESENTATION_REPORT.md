# ScoutMatch AI — Management Presentation Report

**Branch:** `feature/scoutmatch-agent-flow-extension`  
**Status labels:** VERIFIED · RECOMMENDED · MANUAL VALIDATION REQUIRED

---

## 1. One-sentence product description

**VERIFIED:** ScoutMatch AI is an opening-season football recruitment workspace that grounds scouting answers in club documents and coordinates tactical planning, budget-aware player recommendations, lineup review, and sanitized management notifications through a polished web UI backed by Amazon Bedrock.

## 2. Primary user

**VERIFIED:** Scouts / Professional Analysts preparing opening-match recruitment and lineup recommendations.

## 3. Business problem

**VERIFIED:** Clubs must compare documented squad depth, recruitment candidates, and budget constraints quickly without losing auditability or over-committing spend before management approval.

## 4. Opening-season storyline

**VERIFIED:** Before the opening match, the analyst reviews 15 current squad players, 8 pre-scouted external candidates, squad weakness analysis, a right-back comparison, a goalkeeper-injury coach brief, a management-ready player recommendation, a head-coach lineup review, and a visual lineup board.

## 5. Main user journey

**VERIFIED:**

1. Open polished root UI at public ScoutMatch URL.
2. Review collapsed sidebar summaries (club knowledge, recruitment pool).
3. Ask opening-season prompts (weakness analysis, comparisons, coach brief).
4. Pre-confirm player recommendation → Deny or Confirm.
5. Save demo 4-3-3 lineup → Confirm.
6. Generate inline lineup board via private SVG proxy.

## 6–9. Four Agent-facing Tools

| Tool | Trigger | Return value |
|------|---------|--------------|
| **PlanMatchTactics** **VERIFIED** | Coach brief / tactical planning prompt | Formation, style, reasoning, planning context (read-only) |
| **SubmitPlayerSelectionToManagement** **VERIFIED** | Explicit submit + Confirm only | `PENDING_MANAGEMENT_APPROVAL`, remaining budget, SNS status |
| **FinalizeCurrentLineup** **VERIFIED** | Save lineup + Confirm only | `PENDING_HEAD_COACH_REVIEW`, 11 starters |
| **GenerateCurrentLineupBoard** **VERIFIED** | Show current lineup | Private SVG route via Flask proxy |

## 10. Knowledge Base versus DynamoDB

**VERIFIED:**

- **Knowledge Base:** Read-only club documents, candidate profiles, tactical guidance (RAG retrieval).
- **DynamoDB / local ops store:** Session planning context, budget reservations, lineup state, demo season scope.

## 11. Role of Bedrock Agent

**VERIFIED:** Orchestrates exactly four public tools, routes user language to actions, enforces native confirmation for writes, and stays associated with the Knowledge Base.

## 12. Role of Guardrail

**VERIFIED (v11):**

- Central guardrail attached to public alias (version 22).
- **HATE input = NONE** (narrow fix for right-back comparison false positive).
- **INSULTS / SEXUAL input = LOW** (restored from broader NONE).
- **VIOLENCE / MISCONDUCT / PROMPT_ATTACK input = NONE** with topic deny policies for credentials and unauthorized changes.
- **Compensating controls:** application paraphrase fallback, response sanitization, agent instruction, topic deny rules.
- Live regression: right-back comparison, goalkeeper injury, opening formation allowed; credential/private-key/hidden-prompt/injection/override prompts blocked.

## 13. Role of four Lambdas

**VERIFIED:** One dedicated Lambda per tool (no fifth Lambda). Each packages shared football logic, write-confirmation checks, and least-privilege IAM.

## 14. Role of SNS

**OPTIONAL FUTURE EXTENSION (frozen — not part of course demo or submission):**

- DynamoDB management-review record is the source of truth for submitted recommendations.
- SNS publish code is isolated, non-blocking, and safe to ignore for presentation purposes.
- **Not listed as a project blocker.** See `docs/SCOUTMATCH_FINAL_COURSE_READINESS_REPORT.md`.

## 15. Role of private S3 SVG storage

**VERIFIED:** Lineup boards stored privately; UI loads via authenticated Flask proxy (`HTTP 200`, inline SVG, no public S3 URL).

## 16. Role of EC2 and Docker

**VERIFIED:**

- Production: `0.0.0.0:80:5000` → `scoutmatch-ai:agent-extension-v15`
- Staging: `127.0.0.1:5002:5000`
- Rollback: `scoutmatch-ai:baseline-club-v14`

## 17. Recommended 6-slide structure

**RECOMMENDED:**

1. Problem & user (30 s)
2. Opening-season storyline (45 s)
3. Live UI walkthrough (90 s)
4. Four-tool architecture (60 s)
5. Safety & governance (45 s)
6. Business value & next steps (30 s)

## 18. Speaking time per slide

**RECOMMENDED:** ~5 minutes total (see per-slide times above).

## 19. Screenshot list

**VERIFIED (automated HTTP):** health, status, workspace API.  
**MANUAL VALIDATION REQUIRED:** Console screenshots per `docs/SCOUTMATCH_DYNAMIC_SCREENSHOT_GUIDE.md` (viewport, sidebar, system status, AWS Console).

## 20. Live-demo script

**VERIFIED:** See `docs/SCOUTMATCH_FINAL_DEMO_SCRIPT.md` and `scripts/final_hardening_live_rehearsal.py` results.

## 21. Fallback plan

**RECOMMENDED:**

- If Agent slow: show pre-captured responses and Lambda direct invoke output.
- If SNS email missing: show `Management notification: queued` and Console topic screenshot.
- Rollback Docker image to `baseline-club-v14` if UI regression.

## 22. Strongest business-value messages

**RECOMMENDED:** Faster opening-season decisions, budget-safe recommendations, audit-friendly confirmations, management-ready notifications.

## 23. Strongest technical-value messages

**VERIFIED:** Exactly four tools / four Lambdas / four action groups on public alias; guardrail + confirmation gates; KB-grounded RAG; private SVG proxy; full pytest 434 passed.

## 24. Likely manager questions and answers

| Question | Answer |
|----------|--------|
| How do we avoid double spend? | Confirm-gated reservation + idempotent selection **VERIFIED** |
| Can unsafe prompts leak secrets? | Guardrail topic deny + sanitization **VERIFIED** |
| Is email mandatory for demo? | SNS publish can succeed without inbox; email needs subscription **MANUAL** |
| How do we roll back? | `scoutmatch-ai:baseline-club-v14` **VERIFIED** |

## 25. Missing evidence still requiring manual validation

**MANUAL VALIDATION REQUIRED:**

1. Create SNS topic in AWS Console (IAM user lacks SNS create/list).
2. Confirm SNS email subscription from inbox.
3. AWS Console screenshots (KB enabled, guardrail, four action groups on alias version, DynamoDB, private S3 SVG).
4. Desktop viewport screenshots at 1366×768, 1440×900, 1920×1080 (browser automation not installed; use manual checklist in screenshot guide).
