# ScoutMatch Agent Extension Architecture (final)

## Primary user

**Scout / Professional Analyst** preparing opening-season recruitment and lineup recommendations.

## Final runtime flow

```mermaid
flowchart LR
  Browser[Browser root UI /]
  EC2[EC2 Docker Flask]
  Agent[Bedrock Agent]
  GR[Central Guardrail]
  KB[Knowledge Base ENABLED]
  G1[Tactics Action Group]
  G2[Selection Action Group]
  G3[Lineup Action Group]
  G4[Lineup Board Action Group]
  L1[PlanMatchTactics Lambda]
  L2[SubmitPlayerSelection Lambda]
  L3[FinalizeCurrentLineup Lambda]
  L4[GenerateLineupBoard Lambda]
  DDB[DynamoDB operational state]
  S3[Private S3 lineup SVG]
  Proxy[Flask SVG proxy]

  Browser --> EC2 --> Agent
  GR -.-> Agent
  Agent --> KB
  Agent --> G1 --> L1 --> DDB
  Agent --> G2 --> L2 --> DDB
  Agent --> G3 --> L3 --> DDB
  Agent --> G4 --> L4 --> S3 --> Proxy --> Browser
```

## Four public Agent-facing tools

| Tool | Lambda |
|------|--------|
| `PlanMatchTactics` | `ScoutMatchPlanMatchTacticsAvidan` |
| `SubmitPlayerSelectionToManagement` | `ScoutMatchSubmitPlayerSelectionAvidan` |
| `FinalizeCurrentLineup` | `ScoutMatchFinalizeCurrentLineupAvidan` |
| `GenerateCurrentLineupBoard` | `ScoutMatchGenerateLineupBoardAvidan` |

## Principles

- v14 Flask RAG (`/api/sessions/.../messages`) remains available.
- Root UI at `/` is the primary presentation route; `/recruitment-advisor` is diagnostic only.
- Write actions require explicit Confirm; DynamoDB is the source of truth for recommendations.
- SNS is optional and non-blocking.
- Legacy helper Lambdas (budget fit, shortlist, native router) are detached from the public Agent and preserved for rollback only.
- Local deploy state lives in `infra/scoutmatch_agent_extension/.local/` (never commit or package).
