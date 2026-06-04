# ScoutMatch Bedrock Agent Extension

Optional extension for the AWS course. **ScoutMatch AI v14 production RAG is unchanged.**

## Architecture

- **One agent:** `scoutmatch-recruitment-agent-user5-avidan`
- **One guardrail:** `scoutmatch-guardrail-user5-avidan` (attached only to this agent)
- **Four Lambdas** with deterministic Python logic (stdlib only)
- **Four action groups** inside the single agent
- **Knowledge base:** existing `knowledge-base-user5` (read-only association)

## Action groups

| Action group | Lambda | Function |
|--------------|--------|----------|
| ScoutMatchBudgetActionsAvidan | ScoutMatchBudgetImpactAvidan | CalculateBudgetImpact |
| ScoutMatchRightBackActionsAvidan | ScoutMatchRightBackFitAvidan | EvaluateRightBackFit |
| ScoutMatchBelowStrikerActionsAvidan | ScoutMatchBelowStrikerFitAvidan | EvaluateBelowStrikerFit |
| ScoutMatchForwardActionsAvidan | ScoutMatchForwardFitAvidan | EvaluateForwardFit |

## Local code

- `infra/scoutmatch_agent_extension/lambdas/`
- Tests: `infra/scoutmatch_agent_extension/tests/`
- Deploy: `infra/scoutmatch_agent_extension/scripts/deploy_scoutmatch_extension.py`

## Deploy (safe)

```bash
python infra/scoutmatch_agent_extension/scripts/deploy_scoutmatch_extension.py --plan
python infra/scoutmatch_agent_extension/scripts/deploy_scoutmatch_extension.py --apply
```

State is stored only in `infra/scoutmatch_agent_extension/.local/state.json` (gitignored).

## Validate

```bash
python infra/scoutmatch_agent_extension/scripts/validate_scoutmatch_extension.py --lambda-only
python infra/scoutmatch_agent_extension/scripts/invoke_scoutmatch_agent.py "What is the maximum combined annual salary budget for new signings?"
```

## Agent alias

`scoutmatch-recruitment-demo-user5-avidan`

## Production safety

- No EC2 deploy
- No changes to `POST /api/sessions/<id>/messages` (v14 chat)
- No S3 baseline or KB data source modifications
