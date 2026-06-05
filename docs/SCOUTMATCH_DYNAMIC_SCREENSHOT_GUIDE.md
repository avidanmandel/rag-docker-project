# ScoutMatch Dynamic Screenshot Guide

Store PNGs under `submission_evidence/agent_flow_extension/`. Do not fabricate images.

## Baseline v14 (already captured)

See `submission_evidence/final_v14/` — 11 PNGs for KB, EC2, Docker, homepage, grounded answers, refusal, upload, delete, clear.

## Bedrock architecture (required)

| File | Capture |
|------|---------|
| `kb_console_overview.png` | Knowledge Base `knowledge-base-user5` |
| `kb_data_source_sync.png` | Data source sync COMPLETE (includes `scoutmatch/knowledge-base/tactical/` if added) |
| `agent_kb_association_enabled.png` | Agent → Knowledge Bases → state **ENABLED** |
| `agent_guardrail_central.png` | `scoutmatch-guardrail-user5-avidan` attached to agent (one central guardrail) |

## Final four-Lambda architecture (applied)

| File | Capture |
|------|---------|
| `four_action_groups_enabled.png` | Exactly four groups: `ScoutMatchTacticsActionsAvidan`, `ScoutMatchSelectionAgAvidan`, `ScoutMatchLineupActionsAvidan`, `ScoutMatchLineupBoardActionsAvidan` |
| `four_dedicated_lambdas.png` | `ScoutMatchPlanMatchTacticsAvidan`, `ScoutMatchSubmitPlayerSelectionAvidan`, `ScoutMatchFinalizeCurrentLineupAvidan`, `ScoutMatchGenerateLineupBoardAvidan` |
| `legacy_groups_detached.png` | Old native/football groups disabled on agent; Lambdas still exist in console |

## Dynamic sporting-director flow

| File | Capture |
|------|---------|
| `31_dynamic_analyst_chat.png` | Multi-turn polished root UI conversation (coach brief → selection → lineup) |
| `32_squad_planning_context_saved.png` | DynamoDB `SQUAD_CONTEXT` / `TACTICAL_PLAN` item (sanitized) |
| `33_player_selection_confirmation.png` | Bedrock confirmation before budget reservation |
| `37_budget_ledger_record.png` | `RESERVED_PENDING_APPROVAL` ledger entry |
| `34_sns_management_topic.png` | `ScoutMatchManagementNotificationsAvidan` topic |
| `35_sns_publish_evidence.png` | Publish metrics / message preview (no email in repo) |
| `38_lineup_record.png` | Finalized 11-player lineup record |
| `39_private_lineup_svg_s3.png` | Private object under `scoutmatch/football-operations/lineups/` |
| `40_inline_lineup_board_chat.png` | SVG inline in polished root UI chat (Flask proxy route only) |
| `41_lineup_board_433.png` | Full board with 11 own-team markers |
| `42_pending_management_marker.png` | PENDING APPROVAL badge on Ron Ben Ari |

## Required manual screenshot order (16 items)

| # | File | Capture |
|---|------|---------|
| 1 | `agent_kb_association_enabled.png` | Agent → Knowledge Bases → **ENABLED** |
| 2 | `kb_data_source_sync_complete.png` | Data source sync **COMPLETE** (tactical docs included) |
| 3 | `agent_guardrail_central.png` | `scoutmatch-guardrail-user5-avidan` on agent |
| 4 | `four_action_groups_enabled.png` | Four final Action Groups only |
| 5 | `four_dedicated_lambdas.png` | Four dedicated Lambdas |
| 6 | `dynamodb_fallback_operational_state.png` | `football_ops#` operational record (sanitized) |
| 7 | `34_sns_management_topic.png` | SNS topic exists (**optional** — not required for course submission) |
| 8 | `sns_confirmed_email_subscription.png` | Email subscription **Confirmed** (blur email; **optional**) |
| 9 | `33_player_selection_confirmation.png` | Confirmation prompt in Advisor chat |
| 10 | `remaining_budget_after_confirm.png` | Remaining budget after confirm |
| 11 | `39_private_lineup_svg_s3.png` | Private S3 SVG under lineup prefix |
| 12 | `40_inline_lineup_board_chat.png` | Inline SVG in browser chat |
| 13 | `41_ron_ben_ari_right_back.png` | Ron Ben Ari at right-back |
| 14 | `42_pending_management_marker.png` | PENDING_MANAGEMENT_APPROVAL badge |
| 15 | `17_existing_v14_flask_ui_unchanged.png` | v14 homepage still healthy |
| 16 | `public_recruitment_advisor_route.png` | Public `/recruitment-advisor` after EC2 cutover |

## Regression proof

| File | Capture |
|------|---------|
| `17_existing_v14_flask_ui_unchanged.png` | Production homepage unchanged after Advisor work |
| `public_recruitment_advisor_route.png` | `/recruitment-advisor` after optional EC2 cutover |

## Click-by-click: SNS email subscription

See `docs/SCOUTMATCH_SNS_EMAIL_SUBSCRIPTION_GUIDE.md`.

## Click-by-click: Knowledge Base tactical sync

1. AWS Console → Amazon Bedrock → Knowledge bases → `knowledge-base-user5`
2. Data sources → `scoutmatch-player-documents` → Sync history → confirm COMPLETE after tactical upload
3. Agents → `scoutmatch-recruitment-agent-user5-avidan` → Knowledge bases → **ENABLED**

## MANUAL viewport validation (browser automation unavailable)

Capture at **1366×768**, **1440×900**, and **1920×1080**. Save sanitized PNGs under `submission_evidence/agent_flow_extension/viewport/`.

| File | Check |
|------|-------|
| `01_home_opening_season_1366x768.png` | No page-level vertical scrollbar; four opening prompts visible |
| `02_sidebar_collapsed.png` | Groups collapsed; no full player/doc lists |
| `03_sidebar_expanded.png` | Expanded group scrolls internally only |
| `04_system_status_collapsed.png` | System status collapsed by default |
| `05_system_status_expanded.png` | Expanded status shows sanitized labels only |

**Verify:** composer visible, summary cards visible, Markdown rendered (no raw `**`), no internal IDs, no prominent AWS developer labels, chat scrolls inside message area only.

**Automated text evidence:** `python scripts/collect_aws_sanitized_evidence.py` and `python scripts/final_hardening_live_rehearsal.py`.
