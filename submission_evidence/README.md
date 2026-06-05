# Submission Evidence — ScoutMatch AI

## Active release

| Item | Value |
|------|-------|
| Public URL | http://3.239.47.249/ |
| Primary demo route | `/` (polished root UI) |
| Runtime | `agent_extension_enabled=true`, `chat_backend=bedrock_agent` |
| Docker image | `scoutmatch-ai:agent-extension-v15` |

## Evidence folders

| Folder | Purpose |
|--------|---------|
| `final_v14/` | **11 baseline PNGs** — KB, EC2, Docker, homepage, grounded RAG, upload/delete (already captured) |
| `agent_flow_extension/` | **5 required new PNGs** — see `docs/SCOUTMATCH_DYNAMIC_SCREENSHOT_GUIDE.md` |

## Required new screenshots (5)

1. `agent_kb_association_enabled.png`
2. `four_action_groups_enabled.png`
3. `four_dedicated_lambdas.png`
4. `player_selection_confirmation.png`
5. `inline_lineup_board_chat.png`

SNS screenshots are **not required**.

## Packaging

- Include `submission_evidence/final_v14/`, `submission_evidence/agent_flow_extension/`, and this README in the lecturer ZIP.
- Exclude `submission_evidence/archive/`, secrets, `.local/`, and runtime artifacts (enforced by `scripts/prepare_submission_zip.py`).
