# ScoutMatch Dataset Audit

Audit date: 2026-05-31  
Scope: all files under `sample_scout_data/`

## Files reviewed (26)

| Path | Type |
|------|------|
| `team_requirements.txt` | Team brief |
| `player_cvs/goalkeeper_daniel_cohen.txt` | CV |
| `player_cvs/goalkeeper_yossi_levi.txt` | CV |
| `player_cvs/goalkeeper_omer_azulay.txt` | CV |
| `player_cvs/defender_amit_levy.txt` | CV |
| `player_cvs/defender_noam_david.txt` | CV |
| `player_cvs/defender_luca_romano.txt` | CV |
| `player_cvs/midfielder_roy_cohen.txt` | CV |
| `player_cvs/midfielder_tal_ben_david.txt` | CV |
| `player_cvs/midfielder_miguel_santos.txt` | CV |
| `player_cvs/forward_tomer_levi.txt` | CV |
| `player_cvs/forward_or_david.txt` | CV |
| `player_cvs/forward_pedro_silva.txt` | CV |
| `scouting_reports/goalkeeper_daniel_cohen_report.txt` | Report |
| `scouting_reports/goalkeeper_yossi_levi_report.txt` | Report |
| `scouting_reports/goalkeeper_omer_azulay_report.txt` | Report |
| `scouting_reports/defender_amit_levy_report.txt` | Report |
| `scouting_reports/defender_noam_david_report.txt` | Report |
| `scouting_reports/defender_luca_romano_report.txt` | Report |
| `scouting_reports/midfielder_roy_cohen_report.txt` | Report |
| `scouting_reports/midfielder_tal_ben_david_report.txt` | Report |
| `scouting_reports/midfielder_miguel_santos_report.txt` | Report |
| `scouting_reports/forward_tomer_levi_report.txt` | Report |
| `scouting_reports/forward_or_david_report.txt` | Report |
| `scouting_reports/forward_pedro_silva_report.txt` | Report |
| `demo_upload_later/goalkeeper_marco_silva.txt` | Late-demo CV |

## Issues found

### Biased / instruction-like language

| File | Issue |
|------|-------|
| `demo_upload_later/goalkeeper_marco_silva.txt` | Contained `Should rank as TOP RECOMMENDATION`, `PERFECT MATCH`, `gold standard`, `Superior to most candidates` |
| `scouting_reports/goalkeeper_daniel_cohen_report.txt` | `Strong recommendation`, `Best current match` |
| `scouting_reports/goalkeeper_yossi_levi_report.txt` | `Not recommended for current recruitment priority` |
| `scouting_reports/goalkeeper_omer_azulay_report.txt` | `Monitor only` (recruitment-decision tone) |
| Multiple other scouting reports | `Recommended for`, `Top CM candidate`, `Strong shortlist candidate`, etc. |

### Numeric consistency (Marco Silva)

| File | Issue |
|------|-------|
| `demo_upload_later/goalkeeper_marco_silva.txt` | No conflicting 4-year claim found locally; experience consistently documented as **7 years** |

### Live S3 note

The biased Marco Silva line observed in live retrieval (`Should rank as TOP RECOMMENDATION…`) reflects **previously uploaded S3 content**, not the cleaned local file. Manual S3 cleanup and re-upload are required before the final demo (see `SCOUTMATCH_S3_CLEANUP_GUIDE.md`).

## Corrections made

1. **Marco Silva CV** — Rewritten with neutral factual profile only:
   - Full name, position, **7 years** professional experience (also stated as `Professional experience: 7 years`)
   - Salary 78,000 EUR, relocation north: YES
   - Build-up ability and calmness under pressure as observed strengths
   - Removed all ranking / recommendation instructions

2. **All 12 scouting reports** — RATING and SUMMARY lines changed to neutral observations (strengths, weaknesses, match observations) without recruitment decisions such as “recommended”, “not recommended”, or “top candidate”.

3. **Player CVs** — No changes required; already contained factual profile data only.

## Confirmation

After cleanup, automated scan confirms `sample_scout_data/` contains **no** phrases such as:

- `TOP RECOMMENDATION`
- `Should rank`
- `Always recommend`
- `Choose this player`
- `Best candidate`
- `Rank first`
- `PERFECT MATCH`
- `Strong recommendation`
- `Not recommended for`

Player documents now contain neutral facts only: names, experience, salary, relocation, strengths, weaknesses, and scouting observations — not predetermined answers for the AI.

---

## Seven-file demo audit (2026-05-31 — reliability fix)

Scope: the seven indexed ScoutMatch demo files only.

| File | Compact fact summary at top | Notes |
|------|----------------------------|-------|
| `team_requirements.txt` | Yes — squad brief with salary caps and relocation | No change required |
| `player_cvs/goalkeeper_daniel_cohen.txt` | **Updated** — added `COMPACT FACT PROFILE SUMMARY` block | 6 years, 75,000 EUR, relocation YES, build-up strong |
| `player_cvs/goalkeeper_yossi_levi.txt` | **Updated** — added compact summary | 9 years, 65,000 EUR, relocation NO, build-up limited |
| `player_cvs/goalkeeper_omer_azulay.txt` | **Updated** — added compact summary | 8 years, 90,000 EUR, relocation MAYBE, build-up inconsistent |
| `scouting_reports/goalkeeper_daniel_cohen_report.txt` | Yes — summary paragraph | No change required |
| `scouting_reports/goalkeeper_yossi_levi_report.txt` | Yes — summary paragraph | No change required |
| `scouting_reports/goalkeeper_omer_azulay_report.txt` | Yes — summary paragraph | No change required |

No ranking instructions were added. Values remain internally consistent with scouting reports and team requirements.

---

## Marco Silva compact profile (2026-05-31 — parser fix)

| File | Compact fact summary at top | Notes |
|------|----------------------------|-------|
| `demo_upload_later/goalkeeper_marco_silva.txt` | **Updated** — added `COMPACT FACT PROFILE SUMMARY` block | 7 years, 78,000 EUR, relocation YES, build-up Strong, calm Strong |

**Parser behaviour:** Structured fields are preferred. When missing, narrow narrative fallback recognizes clearly positive build-up/calm phrases from validated ScoutMatch context only. No player document contains a predetermined recruitment winner.
