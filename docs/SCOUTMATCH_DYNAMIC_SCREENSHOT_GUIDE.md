# ScoutMatch Dynamic Screenshot Guide

Store PNGs under `submission_evidence/agent_flow_extension/` or a course submission folder. Do not fabricate images.

## Baseline v14 (already captured)

See `submission_evidence/final_v14/` — 11 PNGs for KB, EC2, Docker, homepage, grounded answers, refusal, upload, delete, clear.

## Bedrock architecture (required)

| File | Capture |
|------|---------|
| `kb_console_overview.png` | Knowledge Base `knowledge-base-user5` |
| `kb_data_source_sync.png` | Data source `scoutmatch-player-documents` AVAILABLE / sync COMPLETE |
| `agent_kb_association_enabled.png` | Agent → Knowledge Bases → state **ENABLED** |

## Simplified four-tool Agent (after apply)

| File | Capture |
|------|---------|
| `native_four_tools_only.png` | `ScoutMatchNativeActionsAvidan` lists exactly 4 functions |
| `football_groups_detached.png` | Football action groups disabled/detached; Lambdas still exist |

## Dynamic sporting-director flow

| File | Capture |
|------|---------|
| `31_dynamic_sporting_director_chat.png` | Multi-turn Advisor conversation |
| `32_squad_planning_context_saved.png` | DynamoDB `SQUAD_CONTEXT` item (sanitized) |
| `33_player_selection_confirmation.png` | Bedrock confirmation prompt |
| `37_budget_ledger_record.png` | `RESERVED_PENDING_APPROVAL` ledger entry |
| `34_sns_management_topic.png` | `ScoutMatchManagementNotificationsAvidan` topic |
| `35_sns_publish_evidence.png` | Publish metrics / message preview (no email in repo) |
| `38_lineup_record.png` | Finalized 11-player lineup record |
| `39_private_lineup_svg_s3.png` | Private object under `scoutmatch/football-operations/lineups/` |
| `40_inline_lineup_board_chat.png` | SVG inline in Advisor chat |
| `41_lineup_board_433.png` | Full 4-3-3 board |
| `42_pending_management_marker.png` | PENDING APPROVAL badge on transfer candidate |

## Regression proof

| File | Capture |
|------|---------|
| `17_existing_v14_flask_ui_unchanged.png` | Production homepage unchanged |
