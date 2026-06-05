# ScoutMatch dynamic football operations — Stage One plan

## Product purpose

Upgrade ScoutMatch into a **dynamic AWS-native sporting-director assistant**. The user describes opponents, formations, squad weaknesses, and recruitment choices in natural language. Each confirmed action updates **operational DynamoDB state** so later answers reflect earlier reservations, pending management approvals, and the latest lineup.

**Persona:** sporting director at a small club who may also act as coach/scout.

## Static Knowledge Base vs dynamic DynamoDB

| Source | Holds |
|--------|--------|
| Knowledge Base | Static budget policy, candidate reports, recruitment rules |
| DynamoDB `ScoutMatchFootballOperationsAvidan` | Live context, reservations, selections, lineups, availability |

The Agent must never invent management approval or salaries. Approval status comes only from DynamoDB records.

## Mandatory showcase tools

1. **SubmitPlayerSelectionToManagement** — budget check, reservation, SNS notification, remaining budget.
2. **GenerateCurrentLineupBoard** — SVG tactical board, private S3 object, safe Flask proxy route.

## Supporting operations (implemented locally)

| Function | Purpose |
|----------|---------|
| `UpdateSquadPlanningContext` | Opponent, formation, priorities, operational budget |
| `FinalizeCurrentLineup` | Validate and save 11 starters |
| `RecordPlayerAvailabilityChange` | Optional; implemented, **not** on agent (quota) |
| `AnalyzeSquadDepthGaps` | Optional; implemented, **not** on agent (quota) |

## DynamoDB design

**Table:** `ScoutMatchFootballOperationsAvidan` (on-demand)

| Item type | Key pattern |
|-----------|-------------|
| SQUAD_CONTEXT | `squad_context#current` |
| LINEUP | `lineup#current` |
| PLAYER_SELECTION | `player_selection#{candidate}` |
| BUDGET_LEDGER | `budget_ledger#{id}` |
| AVAILABILITY_UPDATE | `availability#{player}` |

Concise JSON only — no raw CVs, secrets, or full KB documents.

## SNS management flow

**Topic:** `ScoutMatchManagementNotificationsAvidan`

- Lambda publishes sanitized text (no hard-coded email in Git).
- If no email subscription exists, apply stage continues; management receives nothing until a manual SNS subscription is added.

### Manual SNS email subscription (after apply)

1. AWS Console → **Amazon SNS** → **Topics**.
2. Open `ScoutMatchManagementNotificationsAvidan`.
3. **Create subscription** → Protocol **Email** → enter management address.
4. Confirm the subscription from the inbox.
5. Re-run a confirmed `SubmitPlayerSelectionToManagement` test.

## SVG lineup board flow

1. Agent calls `GenerateCurrentLineupBoard`.
2. Lambda reads `lineup#current` from DynamoDB.
3. Python stdlib builds SVG (green pitch, 11 markers, pending-approval badge).
4. SVG saved privately under `scoutmatch/football-operations/lineups/` (no public ACL, no placeholder object).
5. Tool returns `image_route`: `/api/recruitment-advisor/lineups/current/image`.
6. Flask fetches object via boto3 and returns `image/svg+xml`.
7. Recruitment Advisor UI renders the image inline.

## Bedrock confirmation

| Write action | Confirmation |
|--------------|--------------|
| `SubmitPlayerSelectionToManagement` | Required |
| `FinalizeCurrentLineup` | Required |
| `RecordPlayerAvailabilityChange` | Required (direct tests only) |
| `UpdateSquadPlanningContext` | Not required (planning context) |
| `GenerateCurrentLineupBoard` | Not required (renders approved state) |

Native Bedrock `requireConfirmation` on apply; `write_confirmed` for direct tests.

## Idempotency

`SubmitPlayerSelectionToManagement` uses a planning-context idempotency key. Repeated CONFIRM returns `ALREADY_RESERVED` without a second ledger entry.

## Simplified four-tool course design (final)

The Sporting Director sees **exactly four** user-facing Agent Tools in `ScoutMatchNativeActionsAvidan`:

1. `UpdateSquadPlanningContext`
2. `SubmitPlayerSelectionToManagement`
3. `FinalizeCurrentLineup`
4. `GenerateCurrentLineupBoard`

At approved `--apply`, the plan **detaches** the four football Action Groups from the Agent (Lambdas preserved for internal `boto3`/`lambda` invoke). Recruitment shortlist/workflow/brief APIs are **internal helpers only**.

**Deployed state (pre-apply):** Agent draft still shows legacy 4 football + 6 native APIs — documented as PARTIAL in `docs/COURSE_REQUIREMENTS_COMPLIANCE_MATRIX.md`.

## Sample demo conversation

See product spec in Stage One prompt — Barcelona 4-3-3, Ron Ben Ari selection, 43k reservation → 12k remaining, lineup board with pending approval marker.

## Known limitations (plan stage)

- `--apply` not run in Stage One; no AWS mutations.
- Optional tools not exposed on Agent until quota relief.
- Agent alias / Flow unchanged until approved apply.
- Production EC2, Docker v14, S3 baseline, KB content unchanged.

## AWS-only

No external HTTP/HTTPS, scraping, or outbound libraries in extension Lambdas. boto3 + Python stdlib only.
