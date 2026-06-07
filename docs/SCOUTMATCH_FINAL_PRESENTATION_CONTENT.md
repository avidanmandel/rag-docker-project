# ScoutMatch Final Presentation Content (6 slides)

> **Business workflow v2 (2026-06):** Branch `feature/scoutmatch-business-workflow-v2`, feature flag `SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED`. Full spec: `docs/SCOUTMATCH_BUSINESS_WORKFLOW_V2.md`. Rollback: `scoutmatch-ai:baseline-club-v14` and legacy branch `feature/scoutmatch-agent-flow-extension`.

Use this outline to build the manager presentation deck. **No PPTX is committed.** Public demo URL: http://3.239.47.249/

SNS is mentioned only as an optional future extension — not part of the core demo.

---

## Slide 1 — Problem and product idea

**Title:** ScoutMatch AI — evidence-based football recruitment

**Bullets:**
- Small clubs must compare squad depth, candidates, and budget under time pressure.
- Generic chatbots invent player facts; scouts need document-grounded answers only.
- ScoutMatch AI is a Flask web workspace backed by Amazon Bedrock Knowledge Base.
- The analyst prepares recommendations for management and lineups for head-coach review.
- Management approval and signing stay outside the system.

**Speaker notes:** Open with the business pain — wrong signings cost money and squad balance. Position ScoutMatch as a disciplined analyst assistant, not an auto-signing engine.

**Screenshot / diagram:** `05_public_scoutmatch_homepage.png` — polished opening-season landing page.

**Time:** ~45 seconds

---

## Slide 2 — Opening-season storyline

**Title:** One coherent pre-match storyline

**Bullets:**
- 15 current club players and 8 pre-scouted candidates are available at conversation start.
- The analyst reviews squad weaknesses before the opening match.
- Right-back depth and goalkeeper cover drive the recruitment decision.
- A goalkeeper injury coach brief triggers tactical replanning.
- The demo ends with a proposed lineup board for head-coach review.

**Speaker notes:** Walk through the narrative arc: analyze → compare → plan → recommend → lineup. Emphasize that every step uses approved club documents.

**Screenshot:** `31_dynamic_analyst_chat.png` (multi-turn chat — capture during demo rehearsal).

**Time:** ~50 seconds

---

## Slide 3 — User journey

**Title:** What the analyst does in the product

**Bullets:**
- Open the public ScoutMatch UI and ask grounded scouting questions.
- Review source cards tied to Knowledge Base documents.
- Submit a player recommendation — Confirm or Deny before any budget write.
- Save a proposed 4-3-3 demo lineup — Confirm before persistence.
- View the inline lineup board through a private Flask proxy (no public file link).

**Speaker notes:** Stress confirmation gates: nothing is reserved or saved until the analyst explicitly confirms.

**Screenshot:** `33_player_selection_confirmation.png` — Bedrock confirmation card.

**Time:** ~55 seconds

---

## Slide 4 — AWS architecture

**Title:** How ScoutMatch runs on AWS

**Bullets:**
- Browser → EC2 Docker → Flask → Bedrock Agent with central Guardrail.
- Knowledge Base (ENABLED) supplies read-only club and candidate documents.
- Exactly four Action Groups map to four dedicated Lambdas — no fifth tool.
- DynamoDB stores planning context, budget reservations, and lineup state.
- Private S3 stores lineup SVG files; Flask serves them through an authenticated proxy.

**Speaker notes:** Separate static knowledge (KB) from live operational state (DynamoDB). Mention legacy helper Lambdas exist but are detached from the public Agent.

**Screenshot / diagram:** Architecture diagram from README + `four_action_groups_enabled.png` + `four_dedicated_lambdas.png`.

**Time:** ~70 seconds

---

## Slide 5 — Live demo flow

**Title:** 5–7 minute live demo (stable prompts)

**Bullets:**
1. Landing page and opening-season context.
2. Squad weakness analysis with sources.
3. Compare Ron Ben Ari and Tal Cohen within budget.
4. Goalkeeper injury → PlanMatchTactics.
5. Submit Ron Ben Ari → Confirm → pending management approval, 43,000 EUR reserved.
6. Save demo 4-3-3 lineup → Confirm → pending head-coach review.
7. Show inline lineup board (11 players, formation, pending badge).

**Speaker notes:** Follow `docs/SCOUTMATCH_FINAL_DEMO_SCRIPT.md`. If live Agent latency fails, use captured screenshots from `submission_evidence/`.

**Screenshot:** `40_inline_lineup_board_chat.png` — inline SVG in chat.

**Time:** ~90 seconds (demo itself is 5–7 minutes)

---

## Slide 6 — Business value, safety, and next steps

**Title:** Value, safety, and honest boundaries

**Bullets:**
- **Value:** Faster, auditable recruitment prep with visible evidence and budget discipline.
- **Safety:** Central Guardrail blocks credential theft, prompt injection, and off-topic abuse.
- **Boundaries:** Management and head-coach approval are manual steps outside ScoutMatch.
- **Validated:** 437 automated tests; live four-tool validation BLOCKERS=0.
- **Next steps:** Capture remaining Console screenshots; optional future SNS alert extension.

**Speaker notes:** Close honestly — the product prepares decisions; it does not sign players or send binding offers. Previous Advisor threads are not persisted server-side.

**Screenshot:** `agent_guardrail_central.png` + `07_grounded_refusal_for_out_of_scope_questions.png`.

**Time:** ~50 seconds

---

## Total estimated speaking time

**~6–8 minutes** of narration + **5–7 minutes** live demo = fits a standard course presentation slot with Q&A buffer.
