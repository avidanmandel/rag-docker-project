# ScoutMatch AI — Known Limitations

Only limitations verified during release QA (2026-06-03).

## Bedrock ingestion latency

After upload, delete, or clear, retrieval is blocked until `synced_revision` catches up to `document_revision`. Users see an updating/syncing message during this window. Duration depends on Bedrock ingestion queue load (typically tens of seconds to a few minutes).

## Vector index lag

Deleting S3 source objects does not instantly remove embeddings. A successful ingestion job must complete before retrieval reflects the new document set. Historical assistant messages may reference removed documents until the user asks new questions.

## Stale historical answers

When documents change, prior assistant messages remain in the thread but are marked stale when `document_revision_at_answer < document_revision`. The UI badge indicates the answer may not reflect the current upload set.

## Aggregate answer variability (non-deterministic phrasing)

Salary totals, relocation lists, defender comparisons, and availability aggregates use deterministic verification where parsed upload facts exist. Wording may still vary by model, but strict QA requires all expected player names and numeric totals in the answer text.

## Hebrew generation quality

Hebrew answers depend on the configured Bedrock model. Grounding and refusals are enforced; fluency may vary.

Deterministic Hebrew routing covers reusable intents (urgent positions, immediate-availability rationale, cheapest Right Back, combined-budget checks) via synonym patterns — not exact question strings.

## מגן ימני vs בלם ימני

- **מגן ימני** = Right Back (fullback).
- **בלם ימני** = right-sided centre back.

An explicit בלם ימני cheapest-player question does **not** map to Right Back candidates. If no centre-back is documented, the app returns an insufficient-information answer instead of substituting a Right Back.

## Knowledge scopes (baseline + session uploads)

ScoutMatch uses two document layers:

- **Baseline club documents** — shared, read-only, and available in **all** conversations (budget, tactics, squad depth, fixtures, recruitment policy). These live under `scoutmatch/knowledge-base/baseline/production/` and do not require per-session upload.
- **Uploaded candidate documents** — **session-scoped** and isolated per conversation. Each chat session sees only its own uploads under `scoutmatch/knowledge-base/sessions/<session_id>/`.

**Session isolation:** documents uploaded in Session A must never appear in Session B answers or source lists. Cross-session leakage is blocked by session-scoped S3 prefixes, registry filtering, and retrieval validation.

## No admin token / shared candidate corpus

The production build does not expose admin tokens or a shared global **candidate** upload corpus. Candidate uploads remain per-session; baseline club documents are the only shared read-only layer.

## EC2 single-host deployment

No auto-scaling, blue/green fleet, or multi-AZ failover. Rollback is manual via previous Docker image tag and DB backup.

## Shell script line endings

Deploy and validation shell scripts must use Unix (LF) line endings on EC2. Windows CRLF breaks `set -euo pipefail` under bash.

## Corrupt PDF/DOCX and malformed CSV uploads

Upload validation checks extension, size, and basic file structure before S3 ingest. Corrupt PDF/DOCX payloads and CSV files without a `field,value` header (or recognizable player headers) are rejected with HTTP 400. Empty files, unsupported extensions, path traversal filenames, and oversize uploads are also rejected.

## Position-specific cheapest-player queries

Deterministic cheapest-by-position answers (e.g. right back) use upload-time registry facts when the question matches a structured aggregate pattern.

## Compound goalkeeper filters

Deterministic goalkeeper + availability + salary-ceiling questions use registry facts when matched; other compound filters may still rely on LLM retrieval.

## CV + scouting report fact merge

When a scouting report and player CV share the same parsed name, registry merge retains CV structured fields (salary, foot, availability) while scouting reports enrich narrative facts only. Scouting reports cannot seed new registry players without a matching CV document.
