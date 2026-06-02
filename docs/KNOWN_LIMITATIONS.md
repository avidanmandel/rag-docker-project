# ScoutMatch AI — Known Limitations

Only limitations verified during release QA (2026-06-02).

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

## Session-scoped retrieval only

Each conversation sees only its own uploaded documents. There is no cross-session or global knowledge base beyond what was uploaded in that session.

## No admin token / shared corpus

The production session-scoped build does not expose admin tokens or a shared global document corpus. All grounding is per-session.

## EC2 single-host deployment

No auto-scaling, blue/green fleet, or multi-AZ failover. Rollback is manual via previous Docker image tag and DB backup.

## Shell script line endings

Deploy and validation shell scripts must use Unix (LF) line endings on EC2. Windows CRLF breaks `set -euo pipefail` under bash.
