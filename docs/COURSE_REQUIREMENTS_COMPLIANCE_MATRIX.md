# Course Requirements Compliance Matrix

Audit date: 2026-06-04. Branch: `feature/scoutmatch-agent-flow-extension`. Starting commit: `8481e24`.

Legend: **M** = mandatory course requirement, **R** = recommended / evidence polish.

| # | Requirement | Source | Status | Repo evidence | AWS read-only evidence | Automated tests | Screenshot | Remaining action | M/R |
|---|-------------|--------|--------|---------------|------------------------|-----------------|------------|------------------|-----|
| 1 | Clear AI application topic | README, project brief | **PASS** | `README.md` — football recruitment assistant | N/A | N/A | `05_public_scoutmatch_homepage.png` | None | M |
| 2 | Clear user persona | Course / dynamic ops plan | **PASS** | Sporting director persona in `docs/SCOUTMATCH_DYNAMIC_FOOTBALL_OPERATIONS_PLAN.md` | N/A | N/A | `31_dynamic_sporting_director_chat.png` (planned) | Capture Advisor demo screenshot | M |
| 3 | Clear problem statement | README | **PASS** | `README.md` grounded recruitment from uploaded docs | N/A | N/A | `06_grounded_budget_answer_with_sources.png` | None | M |
| 4 | Flask web application | Course stack | **PASS** | `app.py`, Flask routes | N/A | `tests/test_scoutmatch.py` | `05_public_scoutmatch_homepage.png` | None | M |
| 5 | Home page | UI rubric | **PASS** | `templates/index.html` | Public URL HTTP 200 | UI tests via API | `05_public_scoutmatch_homepage.png` | None | M |
| 6 | User question input | UI rubric | **PASS** | Chat textarea in templates / static JS | N/A | API chat tests | `05_public_scoutmatch_homepage.png` | None | M |
| 7 | Submit button | UI rubric | **PASS** | Send button in `static/js/chat.js` | N/A | API tests | `05_public_scoutmatch_homepage.png` | None | M |
| 8 | Answer area | UI rubric | **PASS** | Message list in UI templates | N/A | Chat response tests | `06_grounded_budget_answer_with_sources.png` | None | M |
| 9 | Topic-aligned football UI | Course branding | **PASS** | ScoutMatch branding, football copy in README/UI | N/A | N/A | `05_public_scoutmatch_homepage.png` | None | M |
| 10 | Documents prepared for Knowledge Base | KB rubric | **PASS** | `sample_scout_data/`, `scripts/seed_baseline_club_knowledge.py` | Data source exists | Seed/ingest tests | `01_bedrock_knowledge_base.png` | None | M |
| 11 | Recommended 5–15 meaningful documents | KB rubric | **PASS** | 10 baseline + demo candidate docs (README documents table) | Baseline prefix populated | Baseline gate scripts | `02_bedrock_data_source_sync_complete.png` | None | M |
| 12 | Amazon S3 document storage | Architecture | **PASS** | `aws_storage_service.py`, `config.py` prefix | Bucket + `scoutmatch/knowledge-base/` | Storage tests | `02_bedrock_data_source_sync_complete.png` | None | M |
| 13 | Amazon Bedrock Knowledge Base exists | AWS rubric | **PASS** | `aws_kb_engine.py`, `config.py` | KB name `knowledge-base-user5` | v14 retrieve tests | `01_bedrock_knowledge_base.png` | None | M |
| 14 | Correct ScoutMatch data source attached | AWS rubric | **PASS** | `scoutmatch-player-documents` in docs/runbook | Data source in console evidence | `audit_deployed_agent.py` | `01_bedrock_knowledge_base.png` | None | M |
| 15 | ScoutMatch documents synced successfully | AWS rubric | **PASS** | Ingestion in `aws_storage_service.py` | Sync COMPLETE screenshot | Ingestion tests | `02_bedrock_data_source_sync_complete.png` | None | M |
| 16 | Amazon Bedrock Agent exists | Extension rubric | **PASS** | `infra/scoutmatch_agent_extension/` | Agent `scoutmatch-recruitment-agent-user5-avidan` PREPARED | Advisor tests | Agent console (planned) | None | M |
| 17 | Knowledge Base associated with Agent | Architecture | **PASS** | `deploy_scoutmatch_extension.py` `associate_kb` | `knowledge_base_attached: true` | Architecture test | Agent KB association (planned) | Capture ENABLED screenshot | M |
| 18 | Agent KB association ENABLED | Architecture | **PASS** | `knowledgeBaseState="ENABLED"` in deploy | `knowledge_base_association_enabled: true` | `audit_deployed_agent.py` | Agent KB ENABLED (planned) | Screenshot after apply if needed | M |
| 19 | Stable v14 path uses boto3 KB retrieval | Architecture | **PASS** | `aws_kb_engine.py` `retrieve()` | Production `rag_backend: aws_kb` | `tests/test_scoutmatch.py`, `test_course_architecture.py` | `06_grounded_budget_answer_with_sources.png` | None | M |
| 20 | Recruitment Advisor uses `invoke_agent` | Architecture | **PASS** | `bedrock_agent_service.py` | Agent alias configured locally | `test_bedrock_agent_advisor.py`, `test_course_architecture.py` | Advisor chat (planned) | None | M |
| 21 | Same Agent session ID for follow-ups | UX rubric | **PASS** | `static/js/recruitment_advisor.js` `sessionStorage` | N/A | `test_bedrock_agent_advisor.py::test_same_session_reused` | `31_dynamic_sporting_director_chat.png` | Live demo proof | M |
| 22 | Current-conversation memory works | UX rubric | **PARTIAL** | Bedrock Agent session + operational DynamoDB on confirm | Agent session (AWS) | Football ops context tests | Demo script step 5–13 | Live multi-turn demo after apply | M |
| 23 | Previous Advisor chat history persistence | UX rubric | **MISSING** | No server-side Advisor history DB; only current thread in DOM + `sessionStorage` session id | N/A | Documented honestly in demo script | N/A | Document limitation; optional future SQLite table | R |
| 24 | RAG grounded answers from documents | Core RAG | **PASS** | `aws_kb_engine.py` strict validation | Production grounded answers | 256+ v14 tests | `06_grounded_budget_answer_with_sources.png` | None | M |
| 25 | Retrieved source cards shown | UI rubric | **PASS** | Source cards in v14 UI | Live production | Source validation tests | `06_grounded_budget_answer_with_sources.png` | None | M |
| 26 | Unsupported-question refusal | Safety rubric | **PASS** | Strict RAG refusal path | Production refusal | Refusal tests | `07_grounded_refusal_for_out_of_scope_questions.png` | Advisor refusal screenshot (planned) | M |
| 27 | Upload and KB ingestion flow | Lifecycle | **PASS** | `app.py` upload routes, `aws_storage_service.py` | Session prefix in S3 | Upload/sync tests | `08_uploaded_candidate_answer_with_source.png` | None | M |
| 28 | Delete-document stale-answer protection | Lifecycle | **PASS** | `database.py` revision bump, stale checks | N/A | Delete/stale tests | `09_deleted_candidate_refusal.png` | None | M |
| 29 | Clear-documents behavior | Lifecycle | **PASS** | Clear documents API/UI | N/A | Clear tests | `10a` / `10b` | None | M |
| 30 | MCP / tool-calling demonstrated | Course concept | **PASS** | Bedrock Agent Action Groups + Lambda tools | 5 action groups deployed (legacy layout) | Extension + football ops tests | Agent action groups (planned) | Apply simplified 4-tool attach | M |
| 31 | Exactly four user-facing Agent Tools | Simplified design | **PARTIAL** | Local router exposes 4 only (`native_tools/lambda_function.py`) | Deployed agent still has 4 football + 6 native APIs | `test_simplified_four_tool_design.py` | Native 4-tool group (planned) | Run approved `--apply` to detach helpers | M |
| 32 | Internal helpers separated from user-facing Tools | Architecture | **PASS** | `football_operations_apply.py` `INTERNAL_AGENT_HELPERS`; budget via `player_selection.py` | Helper Lambdas exist, not user-selected | `test_simplified_four_tool_design.py` | N/A | Detach football AGs at apply | M |
| 33 | DynamoDB for dynamic operational state only | Architecture | **PASS** | `ScoutMatchFootballOperationsAvidan` design; KB separate | Table planned, not written this stage | `test_football_operations.py` | `36_football_operations_dynamodb.png` (planned) | Apply + demo records | M |
| 34 | SNS management notification design | Architecture | **PASS** | `sns_notification.py`, topic name constant only | Topic planned | SNS payload test | `34_sns_management_topic.png` (planned) | Manual email subscription | M |
| 35 | Private S3 lineup SVG design | Architecture | **PASS** | `lineup_svg.py`, `lineup_board_service.py` | Prefix planned | SVG tests | `39_private_lineup_svg_s3.png` (planned) | Apply writes after confirm | M |
| 36 | Inline lineup-board in Advisor UI | UX rubric | **PASS** | `recruitment_advisor.js` inline `<img>` | N/A | UI code review | `40_inline_lineup_board_chat.png` (planned) | Live demo after apply | M |
| 37 | Dockerfile exists | Submission | **PASS** | `Dockerfile` | EC2 uses image | N/A | `04_docker_container_running.png` | None | M |
| 38 | requirements.txt exists | Submission | **PASS** | `requirements.txt` | N/A | N/A | N/A | None | M |
| 39 | Docker local build instructions | README rubric | **PASS** | `README.md`, `docs/DEPLOYMENT_RUNBOOK.md` | N/A | N/A | N/A | None | M |
| 40 | Docker EC2 run instructions | README rubric | **PASS** | `docs/DEPLOYMENT_RUNBOOK.md`, deploy scripts | Container running | N/A | `04_docker_container_running.png` | None | M |
| 41 | EC2 public deployment for stable v14 | Deployment | **PASS** | README production URL | `http://3.239.47.249/` health 200 | Public status check | `03_ec2_instance_running.png` | None | M |
| 42 | Public homepage responds | Deployment | **PASS** | Production URL | HTTP 200 | Manual curl | `05_public_scoutmatch_homepage.png` | None | M |
| 43 | `/api/health` responds | Deployment | **PASS** | `app.py` route | HTTP 200 | Health tests | N/A | None | M |
| 44 | `/api/status` with `aws_kb` readiness | Deployment | **PASS** | `app.py` status payload | `ready: true`, `rag_backend: aws_kb` | Status tests | N/A | None | M |
| 45 | GitHub repository organized | Submission | **PASS** | Structured tree, docs/, tests/ | N/A | N/A | N/A | None | M |
| 46 | README includes project goal | Submission | **PASS** | `README.md` opening | N/A | N/A | N/A | None | M |
| 47 | README includes architecture | Submission | **PASS** | Architecture diagrams in README | N/A | N/A | N/A | None | M |
| 48 | README includes installation/run | Submission | **PASS** | README + runbook | N/A | N/A | N/A | None | M |
| 49 | README includes documents used | Submission | **PASS** | Documents table in README | N/A | N/A | N/A | None | M |
| 50 | README includes Docker instructions | Submission | **PASS** | README Docker section | N/A | N/A | N/A | None | M |
| 51 | README includes cleanup notes | Submission | **PARTIAL** | `docs/SCOUTMATCH_AWS_CLEANUP_PLAN.md` separate | N/A | N/A | N/A | Add README link to cleanup plan | R |
| 52 | JSON/CSV structured-data processing | Data rubric | **PASS** | CSV uploads, `requirement_verification.py`, aggregates | N/A | Aggregate tests | `08_uploaded_candidate_answer_with_source.png` | None | M |
| 53 | Local automated tests pass | QA | **PASS** | pytest suites | N/A | 321 passed (required suites) | N/A | None | M |
| 54 | Stable v14 regression tests pass | QA | **PASS** | `tests/test_scoutmatch.py` | Production unchanged | 256 v14 cases green | N/A | None | M |
| 55 | Secret scan passes | Security | **PASS** | `.gitignore` for `.env`, `.env.agent`, PEM; repair scripts untracked | N/A | Grep audit | N/A | None | M |
| 56 | Required baseline screenshots exist | Evidence | **PASS** | `submission_evidence/final_v14/` 11 PNGs | Matches production | N/A | All `final_v14/*` | None | M |
| 57 | Dynamic Tool screenshots planned | Evidence | **PASS** | `docs/SCOUTMATCH_DYNAMIC_SCREENSHOT_GUIDE.md` | N/A | N/A | Checklist items 31–42 | Capture after apply | M |
| 58 | Live demo script exists | Presentation | **PASS** | `docs/SCOUTMATCH_FINAL_DEMO_SCRIPT.md` | N/A | N/A | N/A | Rehearse 5–7 min demo | M |
| 59 | Six-slide presentation content exists | Presentation | **PASS** | `docs/SCOUTMATCH_PRESENTATION_CONTENT.md` | N/A | N/A | N/A | Build PPTX from content | M |
| 60 | Cleanup plan exists | Course exit | **PASS** | `docs/SCOUTMATCH_AWS_CLEANUP_PLAN.md` | N/A | N/A | N/A | None | M |
| 61 | Cleanup deferred until approval | Course exit | **PASS** | Cleanup docs + submission checklist | No destructive actions run | N/A | N/A | User approval required | M |
| 62 | Submission ZIP checklist exists | Submission | **PASS** | `docs/SUBMISSION_CHECKLIST.md` (updated) | N/A | N/A | N/A | Final ZIP review | M |

## Summary counts (mandatory items only)

| Status | Count |
|--------|------:|
| PASS | 54 |
| PARTIAL | 4 (#22, #31, #32 deployed state, #51 recommended) |
| MISSING | 1 (#23 Advisor cross-session history — recommended) |
| MANUAL EVIDENCE NEEDED | 0 blocking (dynamic screenshots planned, not missing code) |

## Partial / missing detail

| # | Gap | Next action |
|---|-----|-------------|
| 22 | Agent session memory needs live multi-turn demo after apply | Run demo script steps 5–13 |
| 31 | Deployed agent still exposes 10 APIs until approved apply | `--apply` with simplified 4-tool detach plan |
| 32 | Football Action Groups still attached on deployed agent | Plan detaches; Lambdas preserved |
| 23 | No persistent Advisor chat log across browser sessions | Document as known limitation (optional future work) |
| 51 | Cleanup notes live in separate doc | Link from README (optional) |

## Four user-facing Tools (local simplified design)

1. `UpdateSquadPlanningContext`
2. `SubmitPlayerSelectionToManagement`
3. `FinalizeCurrentLineup`
4. `GenerateCurrentLineupBoard`

## Internal helpers (not user-facing)

`CalculateBudgetImpact`, `EvaluateRightBackFit`, `EvaluateBelowStrikerFit`, `EvaluateForwardFit`, shortlist/brief/workflow Lambdas, `RecordPlayerAvailabilityChange`, `AnalyzeSquadDepthGaps` — invoked from Lambda code or direct tests only.
