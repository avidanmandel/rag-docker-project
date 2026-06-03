# Submission Evidence — ScoutMatch AI (baseline-club-v14)

This folder holds **final submission screenshots** for the active production release.

## Active release

| Item | Value |
|------|-------|
| Docker image | `scoutmatch-ai:baseline-club-v14` |
| Public URL | http://3.239.47.249/ |
| Production container | `scoutmatch-ai` |
| RAG backend | Amazon Bedrock Knowledge Base (`scoutmatch-player-documents`) |

No AWS resources, Docker containers, or application code were modified during the evidence organization pass (2026-06-03).

## Final submission screenshots (`final_v14/`)

These eleven PNG files are the **only screenshots** to include in the lecturer submission ZIP.

| File | What it proves |
|------|----------------|
| `01_bedrock_knowledge_base.png` | Bedrock Knowledge Base exists and the ScoutMatch data source is attached |
| `02_bedrock_data_source_sync_complete.png` | Active data source AVAILABLE; latest sync COMPLETE; failed files 0; warnings 0 |
| `03_ec2_instance_running.png` | Production EC2 instance running |
| `04_docker_container_running.png` | Container `scoutmatch-ai` on image `baseline-club-v14`, port 80→5000, restart unless-stopped |
| `05_public_scoutmatch_homepage.png` | Public ScoutMatch AI homepage loads |
| `06_grounded_budget_answer_with_sources.png` | Grounded aggregate answer with source cards |
| `07_grounded_refusal_for_out_of_scope_questions.png` | Strict RAG refusal with no sources for out-of-scope question |
| `08_uploaded_candidate_answer_with_source.png` | Session-scoped answer from uploaded candidate document |
| `09_deleted_candidate_refusal.png` | After document delete, stale facts are refused |
| `10a_before_clear_documents_two_files.png` | Two uploaded session documents visible before clear |
| `10b_after_clear_documents_refusal.png` | After clear documents, session-scoped questions are refused |

## Archived material (do **not** include in submission ZIP)

Older evidence from pre-v14 releases lives in the external local archive (`Avidan_RAG_Docker_Project_local_archive/old_evidence/`), not in this repository.

## Packaging

The lecturer submission package includes `submission_evidence/final_v14/` and this README only. Archive folders and secrets are excluded.
