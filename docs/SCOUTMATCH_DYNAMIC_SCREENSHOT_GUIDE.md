# ScoutMatch Manual Screenshot Checklist (minimal)

> **Business workflow v2 (2026-06):** Branch `feature/scoutmatch-business-workflow-v2`, feature flag `SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED`. Full spec: `docs/SCOUTMATCH_BUSINESS_WORKFLOW_V2.md`. Rollback: `scoutmatch-ai:baseline-club-v14` and legacy branch `feature/scoutmatch-agent-flow-extension`.

Store new PNGs under `submission_evidence/agent_flow_extension/`.

**Five required new screenshots** for the Agent extension presentation.  
**SNS screenshots are not required.**

Existing v14 screenshots in `submission_evidence/final_v14/` remain useful background evidence (KB, EC2, Docker, grounded RAG, upload/delete).

---

## Automatically validated (no manual capture)

| Check | Command |
|-------|---------|
| Public homepage / health / status | `python scripts/validate_public_production_gate.py` |
| Four-tool live flows | `python infra/scoutmatch_agent_extension/scripts/validate_public_alias_four_tool.py` |
| Full rehearsal | `python scripts/final_course_readiness_rehearsal.py` |
| ZIP safety | `python scripts/prepare_submission_zip.py` |
| Secret scan | `python scripts/run_secret_scan.py` |

---

## Required manual screenshots (5)

### 1. `agent_kb_association_enabled.png`

| Field | Detail |
|-------|--------|
| **Path** | Amazon Bedrock Console → Agents → your ScoutMatch agent → **Knowledge bases** |
| **Must show** | Association state **ENABLED** |
| **Hide / blur** | Agent IDs, Alias IDs, account IDs, ARNs |
| **Presentation use** | Slide 4 — AWS architecture |

### 2. `four_action_groups_enabled.png`

| Field | Detail |
|-------|--------|
| **Path** | Amazon Bedrock Console → Agents → **Action groups** |
| **Must show** | Exactly four enabled final Action Groups (Tactics, Selection, Lineup, Lineup Board) |
| **Hide / blur** | ARNs and internal IDs |
| **Presentation use** | Slide 4 — AWS architecture |

### 3. `four_dedicated_lambdas.png`

| Field | Detail |
|-------|--------|
| **Path** | AWS Lambda Console → Functions (filter `ScoutMatch`) |
| **Must show** | Four final dedicated Lambda names (PlanMatchTactics, SubmitPlayerSelection, FinalizeCurrentLineup, GenerateLineupBoard) |
| **Hide / blur** | Account IDs and ARNs |
| **Presentation use** | Slide 4 — AWS architecture |

### 4. `player_selection_confirmation.png`

| Field | Detail |
|-------|--------|
| **Path** | Browser → http://3.239.47.249/ (root UI) after Ron Ben Ari submit prompt |
| **Must show** | Ron Ben Ari recommendation with **Confirm / Deny** card before any write |
| **Hide / blur** | Internal IDs, session tokens |
| **Presentation use** | Slide 3 — User journey / Slide 5 — Live demo |

### 5. `inline_lineup_board_chat.png`

| Field | Detail |
|-------|--------|
| **Path** | Browser → http://3.239.47.249/ after *Show me the current proposed lineup* |
| **Must show** | Inline 4-3-3 board, 11 players, proposed-lineup / pending head-coach review status |
| **Hide / blur** | Internal routes, tokens, public S3 URLs |
| **Presentation use** | Slide 5 — Live demo |

---

## After capture

1. Save all five PNGs under `submission_evidence/agent_flow_extension/`.
2. Run `python scripts/prepare_submission_zip.py`.
3. Mark `docs/SCOUTMATCH_SUBMISSION_READINESS_REPORT.md` as **FINAL**.
