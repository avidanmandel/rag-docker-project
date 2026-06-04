# ScoutMatch AWS Resource Inventory (sanitized)

**Region:** `us-east-1`  
**Audit mode:** read-only  
**Account ID:** redacted in committed documentation  

## Classification legend

| Class | Meaning |
|-------|---------|
| ACTIVE_NEW | New extension resources for this task |
| LEGACY_DEMO_KEEP | Older Avidan demo — do not modify or delete |
| SHARED_READ_ONLY | Shared course KB — attach only, never modify |
| REVIEW_REQUIRED | Needs human review before any change |

## Knowledge Base (SHARED_READ_ONLY)

| Name | ID (sanitized) | Status |
|------|----------------|--------|
| knowledge-base-user5 | `KOHOL***` | ACTIVE |

### Data sources

| Name | Status | Prefix / role | Class |
|------|--------|---------------|-------|
| scoutmatch-player-documents | AVAILABLE | `scoutmatch/knowledge-base/` | SHARED_READ_ONLY (production ScoutMatch) |
| knowledge-base-quick-start-k5idl-data-source | AVAILABLE | `data/` (legacy) | REVIEW_REQUIRED — do not attach to new agent |

## Agents

| Name | Class | Notes |
|------|-------|-------|
| agent-quick-user5-avidan | LEGACY_DEMO_KEEP | Legacy datetime demo — unchanged |
| scoutmatch-recruitment-agent-user5-avidan | ACTIVE_NEW | Created by extension deploy |

## Flows

| Name | Class | Notes |
|------|-------|-------|
| flow-avidan-user5 | LEGACY_DEMO_KEEP | Legacy demo — unchanged |
| scoutmatch-recruitment-flow-user5-avidan | ACTIVE_NEW | Three-node recruitment flow |

## Lambda (Avidan / ScoutMatch names only)

| Name | Class |
|------|-------|
| ScoutMatchWeatherAvidan | LEGACY_DEMO_KEEP |
| ScoutMatchLiveToolsAvidan | LEGACY_DEMO_KEEP |
| ScoutMatchBudgetImpactAvidan | ACTIVE_NEW |
| ScoutMatchRightBackFitAvidan | ACTIVE_NEW |
| ScoutMatchBelowStrikerFitAvidan | ACTIVE_NEW |
| ScoutMatchForwardFitAvidan | ACTIVE_NEW |

## Guardrails

| Name | Class |
|------|-------|
| scoutmatch-guardrail-user5-avidan | ACTIVE_NEW |
| avidan_clinic_guardrail-user5 | LEGACY_DEMO_KEEP (not observed in latest list API page — treat as legacy if present) |

## Regenerate inventory

```bash
python infra/scoutmatch_agent_extension/scripts/audit_aws_resources.py
```

Do not commit raw JSON containing account IDs or unrelated student resource names.
