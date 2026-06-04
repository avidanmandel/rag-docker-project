# ScoutMatch AWS Cleanup Plan (PLAN ONLY)

**Do not execute without explicit approval.** This plan targets **only** the new extension resources.

## Order of removal (after course submission approval)

1. Set `SCOUTMATCH_FLOW_EXTENSION_ENABLED=false` locally (never commit `.env.agent`).
2. Delete flow alias `scoutmatch-recruitment-flow-demo-user5-avidan`.
3. Delete flow versions for `scoutmatch-recruitment-flow-user5-avidan`.
4. Delete flow `scoutmatch-recruitment-flow-user5-avidan`.
5. Delete agent alias `scoutmatch-recruitment-demo-user5-avidan`.
6. Delete agent `scoutmatch-recruitment-agent-user5-avidan` (draft and prepared versions).
7. Delete guardrail `scoutmatch-guardrail-user5-avidan` (all versions).
8. Remove Lambda resource-based policies, then delete:
   - ScoutMatchBudgetImpactAvidan
   - ScoutMatchRightBackFitAvidan
   - ScoutMatchBelowStrikerFitAvidan
   - ScoutMatchForwardFitAvidan
9. Delete IAM roles:
   - ScoutMatchExtensionLambdaRoleAvidan
   - ScoutMatchExtensionAgentRoleAvidan
   - ScoutMatchExtensionFlowRoleAvidan
10. Delete local state `infra/scoutmatch_agent_extension/.local/` (gitignored).

## Never delete in this plan

- `knowledge-base-user5` or its data sources
- Production S3 baseline `scoutmatch/knowledge-base/baseline/production/`
- EC2 / Docker production `scoutmatch-ai`
- Legacy demo: `agent-quick-user5-avidan`, `flow-avidan-user5`, `ScoutMatchWeatherAvidan`, `ScoutMatchLiveToolsAvidan`

## Script

```bash
python infra/scoutmatch_agent_extension/scripts/cleanup_plan_only.py
```
