# ScoutMatch Recruitment Extension Architecture

```mermaid
flowchart LR
  User[User / Flask optional endpoint]
  Flow[scoutmatch-recruitment-flow-user5-avidan]
  Agent[scoutmatch-recruitment-agent-user5-avidan]
  GR[scoutmatch-guardrail-user5-avidan]
  KB[knowledge-base-user5]
  L1[ScoutMatchBudgetImpactAvidan]
  L2[ScoutMatchRightBackFitAvidan]
  L3[ScoutMatchBelowStrikerFitAvidan]
  L4[ScoutMatchForwardFitAvidan]

  User --> Flow
  Flow --> Agent
  GR -.-> Agent
  Agent --> KB
  Agent --> L1
  Agent --> L2
  Agent --> L3
  Agent --> L4
```

## Principles

- v14 Flask RAG (`/api/sessions/.../messages`) is unchanged.
- Legacy demo resources are never modified.
- Lambdas use only baseline document rules (no invented facts).
- Deploy is idempotent; default mode is `--plan`.
