# Demo Prompt Ground Truth

Synthetic fictional demo data. Maps landing-page prompts to expected grounded evidence.

## Prompt 1: Squad weaknesses

**Query:** Analyze our current squad weaknesses before the opening match.

**Expected sources:** squad_depth_analysis.md, current_club_squad.csv, opening_season_storyline.md

**Expected themes:** right-back depth HIGH, goalkeeper cover HIGH, Daniel Levy fitness concern

## Prompt 2: Right-back comparison

**Query:** Compare the right-back candidates within our budget.

**Expected sources:** recruitment_candidate_pool.csv, Ron Ben Ari profile, Tal Cohen profile, recruitment_budget_policy.md

**Expected answer elements:** Ron Ben Ari 43,000 EUR aggressive; Tal Cohen 38,000 EUR disciplined budget option

## Prompt 3: Goalkeeper injury

**Query:** Coach brief — starting goalkeeper injured for three matches.

**Expected tool:** PlanMatchTactics (read-only)

**Expected themes:** goalkeeper priority, reserve Daniel Park, compare Omer Azulay vs Yossi Levi, compact defensive proposal

## Prompt 4: Opening formation

**Query:** Recommend a formation for the opening match based on current squad.

**Expected tool:** PlanMatchTactics (read-only)

**Expected themes:** 4-3-3 if full squad available; 5-4-1 if full-backs missing; reference 11 likely starters

## Secondary: Show proposed lineup

**Query:** Show me the current proposed lineup.

**Expected tool:** GenerateCurrentLineupBoard if lineup saved; otherwise explain no proposed lineup exists yet

## Additional grounded queries supported

- Which goalkeeper is better for build-up play? → **Omer Azulay**
- Which goalkeeper is the stronger shot-stopper? → **Yossi Levi**
- Which midfielder performs well under pressure? → **Roy Cohen**
- Show candidates willing to relocate → **Miguel Santos**, Ron Ben Ari, Tal Cohen (relocation_willingness=yes)
