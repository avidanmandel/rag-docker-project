# ScoutMatch Screenshot Checklist (short)

Store PNGs under `submission_evidence/agent_flow_extension/`.  
Baseline v14 screenshots already exist in `submission_evidence/final_v14/` (11 PNGs).

**SNS screenshots are not required** for course submission.

---

## A. Automatically validated (Cursor / scripts — no manual capture needed)

| Item | Validation command / evidence |
|------|-------------------------------|
| Public health | `curl http://3.239.47.249/api/health` → 200 |
| Homepage HTTP 200 | `curl http://3.239.47.249/` → 200 |
| Four-tool live flows | `python infra/scoutmatch_agent_extension/scripts/validate_public_alias_four_tool.py` → BLOCKERS=0 |
| Full live rehearsal | `python scripts/final_course_readiness_rehearsal.py` → BLOCKERS=0 |
| Guardrail regression | `python scripts/run_guardrail_regression.py` → BLOCKERS=0 |
| Automated tests | `python -m pytest -q` → 437 passed |
| Sanitized AWS evidence | `python scripts/collect_aws_sanitized_evidence.py` → JSON artifact |
| Secret scan | `python scripts/run_secret_scan.py` → REVIEW (no live keys) |

---

## B. Manual screenshots required (short ordered list)

### 1. `agent_kb_association_enabled.png`

| Field | Detail |
|-------|--------|
| **Where** | AWS Console → Amazon Bedrock → Agents → `scoutmatch-recruitment-agent-user5-avidan` → Knowledge bases |
| **Must show** | Knowledge base association state **ENABLED** |
| **Hide / blur** | Full ARNs, account ID, alias IDs |
| **Slide** | Slide 4 — AWS architecture |

### 2. `kb_data_source_sync_complete.png`

| Field | Detail |
|-------|--------|
| **Where** | AWS Console → Bedrock → Knowledge bases → `knowledge-base-user5` → Data sources → sync history |
| **Must show** | Status **COMPLETE** (tactical docs included) |
| **Hide / blur** | Bucket ARN, data source IDs |
| **Slide** | Slide 4 — AWS architecture |

### 3. `agent_guardrail_central.png`

| Field | Detail |
|-------|--------|
| **Where** | AWS Console → Bedrock → Agents → Guardrail section |
| **Must show** | `scoutmatch-guardrail-user5-avidan` attached (central guardrail) |
| **Hide / blur** | Guardrail version ARN details |
| **Slide** | Slide 6 — Safety |

### 4. `four_action_groups_enabled.png`

| Field | Detail |
|-------|--------|
| **Where** | AWS Console → Bedrock → Agents → Action groups |
| **Must show** | Exactly four enabled groups: Tactics, Selection, Lineup, Lineup Board |
| **Hide / blur** | Action group IDs, Lambda ARNs |
| **Slide** | Slide 4 — AWS architecture |

### 5. `four_dedicated_lambdas.png`

| Field | Detail |
|-------|--------|
| **Where** | AWS Console → Lambda → Functions (filter `ScoutMatch`) |
| **Must show** | Four final Lambdas: PlanMatchTactics, SubmitPlayerSelection, FinalizeCurrentLineup, GenerateLineupBoard |
| **Hide / blur** | Full function ARNs |
| **Slide** | Slide 4 — AWS architecture |

### 6. `33_player_selection_confirmation.png`

| Field | Detail |
|-------|--------|
| **Where** | Browser → http://3.239.47.249/ → chat after submit prompt |
| **Must show** | Confirm / Deny confirmation card before budget write |
| **Hide / blur** | Session IDs, internal trace IDs |
| **Slide** | Slide 3 — User journey |

### 7. `remaining_budget_after_confirm.png`

| Field | Detail |
|-------|--------|
| **Where** | Browser → same chat after Confirm |
| **Must show** | Pending management approval; reserved 43,000 EUR; remaining 57,000 EUR |
| **Hide / blur** | Internal status codes, planning context IDs |
| **Slide** | Slide 5 — Live demo |

### 8. `40_inline_lineup_board_chat.png`

| Field | Detail |
|-------|--------|
| **Where** | Browser → after *Show me the current proposed lineup* |
| **Must show** | Inline SVG board in chat; Flask proxy route only |
| **Hide / blur** | Public S3 URLs (must not appear) |
| **Slide** | Slide 5 — Live demo |

### 9. `39_private_lineup_svg_s3.png`

| Field | Detail |
|-------|--------|
| **Where** | AWS Console → S3 → bucket → `scoutmatch/football-operations/lineups/` |
| **Must show** | Private SVG object (no public ACL) |
| **Hide / blur** | Bucket name if sensitive; full object ARN |
| **Slide** | Slide 4 — AWS architecture |

### 10. `dynamodb_fallback_operational_state.png`

| Field | Detail |
|-------|--------|
| **Where** | AWS Console → DynamoDB → `ScoutMatchRecruitmentShortlistAvidan` → Explore items → `football_ops#` prefix |
| **Must show** | Sanitized player selection or budget ledger record |
| **Hide / blur** | Personal data, full table ARN |
| **Slide** | Slide 4 — AWS architecture |

---

## Optional viewport captures (browser only)

If time permits, capture at 1440×900 under `submission_evidence/agent_flow_extension/viewport/`:

- `01_home_opening_season.png` — no page scrollbar; four quick-start prompts visible
- `02_sidebar_collapsed.png` — collapsed sidebar groups

---

## After screenshots

1. Verify filenames match the table above.
2. Run `python scripts/prepare_submission_zip.py`.
3. Update `docs/SCOUTMATCH_SUBMISSION_READINESS_REPORT.md` status to **FINAL**.
