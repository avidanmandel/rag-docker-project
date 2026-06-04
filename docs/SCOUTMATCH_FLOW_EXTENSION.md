# ScoutMatch Bedrock Flow Extension

## Flow

- **Name:** `scoutmatch-recruitment-flow-user5-avidan`
- **Alias:** `scoutmatch-recruitment-flow-demo-user5-avidan`
- **Nodes (3):**
  1. `ScoutMatchFlowInput` → output `document` (String)
  2. `ScoutMatchRecruitmentAgentNode` → Agent alias `scoutmatch-recruitment-demo-user5-avidan`
  3. `ScoutMatchFlowOutput` → input `document` from agent response

## Connections

- `ScoutMatchFlowInput.document` → `ScoutMatchRecruitmentAgentNode.agentInputText`
- `ScoutMatchRecruitmentAgentNode.agentResponse` → `ScoutMatchFlowOutput.document`

## Flask (optional, disabled by default)

- Endpoint: `POST /api/recruitment-flow/chat`
- Service: `bedrock_flow_service.py`
- Flags: copy `.env.agent.example` → `.env.agent` (local only, never commit)

```env
SCOUTMATCH_FLOW_EXTENSION_ENABLED=false
SCOUTMATCH_FLOW_ID=
SCOUTMATCH_FLOW_ALIAS_ID=
```

## Invoke via CLI

```bash
python infra/scoutmatch_agent_extension/scripts/invoke_scoutmatch_flow.py "Summarize the winter transfer budget."
```

## Legacy

`flow-avidan-user5` remains unchanged (LEGACY_DEMO_KEEP).
