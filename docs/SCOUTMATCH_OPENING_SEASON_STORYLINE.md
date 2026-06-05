# Opening-Season Storyline

## Who uses ScoutMatch AI

**Scout / Recruitment Analyst / Professional Assistant** — not the head coach, not management.

## Season setup

At the start of a new season ScoutMatch FC has:

- 15 current club players (11 likely starters, 4 rotation)
- 8 pre-scouted external recruitment candidates
- Preloaded club knowledge in the Bedrock Knowledge Base
- 100,000 EUR combined recruitment budget cap

## Analyst workflow

1. Review squad weaknesses before the opening match
2. Compare right-back and goalkeeper candidates within budget
3. Respond to coach briefs (injury, suspension, unavailability)
4. Propose tactical adjustments for head-coach review (read-only via PlanMatchTactics)
5. Submit player recommendations to management (confirmation required)
6. Save proposed lineups for head-coach review (confirmation required)
7. Display proposed lineup boards via safe Flask proxy

## Correct status wording

- Recommendation submitted → **PENDING_MANAGEMENT_APPROVAL**
- Proposed lineup saved → **PENDING_HEAD_COACH_REVIEW**

Never claim a player was signed or that management or the head coach approved a decision.

## UI data groups

1. **Club Knowledge** — preloaded opening-season documents
2. **Recruitment Candidate Pool** — 8 external scouting profiles
3. **Uploaded Candidate Documents** — session uploads only

Clear Documents affects session uploads only.
