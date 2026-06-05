# ScoutMatch Opening-Season Dataset

Synthetic fictional demo data for the opening-season scouting workspace.

## Location

- Local: `infra/scoutmatch_agent_extension/demo_data/opening_season/`
- S3 namespace: `scoutmatch/knowledge-base/opening-season/v1/`
- Demo-season DynamoDB scope: `opening-season-demo-v1`

## Contents

| File | Purpose |
|------|---------|
| `opening_season_storyline.md` | Business storyline and analyst role |
| `current_club_squad.csv` | 15 current club players |
| `squad_depth_analysis.md` | Weaknesses and likely XI |
| `recruitment_candidate_pool.csv` | 8 external candidates |
| `recruitment_budget_policy.md` | 100,000 EUR cap rules |
| `opening_fixture_brief.md` | Opening match context |
| `coach_tactical_principles.md` | Preferred systems |
| `demo_prompt_ground_truth.md` | Landing prompt expectations |
| `candidates/*.md` | One scouting profile per external candidate |

## Upload

```bash
python scripts/upload_opening_season_knowledge.py --apply --wait-sync
```

Additive only — does not delete baseline documents.

## Counts

- Current club players: **15** (11 likely starters, 4 rotation)
- External candidates: **8** (2 GK, 2 RB, 1 CB, 2 MF, 1 ST)
