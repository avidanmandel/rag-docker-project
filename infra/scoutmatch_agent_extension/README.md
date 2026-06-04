# ScoutMatch Agent + Flow Extension

Isolated optional AWS Bedrock extension for the ScoutMatch AI course project.

## Quick start

```bash
python -m pytest infra/scoutmatch_agent_extension/tests -q
python infra/scoutmatch_agent_extension/scripts/deploy_scoutmatch_extension.py --plan
python infra/scoutmatch_agent_extension/scripts/deploy_scoutmatch_extension.py --apply
```

## Layout

- `lambdas/` — four deterministic Action Group handlers + `common/bedrock_response.py`
- `tests/` — unit tests (no live AWS)
- `scripts/` — deploy, audit, validate, invoke, cleanup plan
- `evidence/` — screenshot checklist
- `.local/` — gitignored deploy state

See `docs/SCOUTMATCH_AGENT_EXTENSION.md` and `docs/SCOUTMATCH_FLOW_EXTENSION.md`.
