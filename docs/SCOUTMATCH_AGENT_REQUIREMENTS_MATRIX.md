# ScoutMatch Agent Requirements Matrix

Rules are taken only from project baseline documents and the task specification. No invented thresholds.

| Requirement | Source file | Implementation | Validation | Status |
|-------------|-------------|----------------|------------|--------|
| Max combined annual salary 100,000 EUR | `transfer_budget.txt` | Lambda `CalculateBudgetImpact` | `test_budget_impact.py`, agent prompt #2–3 | Implemented (local) |
| Max standard salary 60,000 EUR | `transfer_budget.txt` | Lambda `CalculateBudgetImpact` | `test_budget_impact.py` | Implemented (local) |
| Emergency starter up to 70,000 EUR | `transfer_budget.txt` | Lambda `CalculateBudgetImpact` | `test_budget_needs_exception` | Implemented (local) |
| State whether proposal stays within budget | `transfer_budget.txt` | Lambda `within_budget_statement` field | Unit tests | Implemented (local) |
| Right-back: immediate availability preferred | `coach_tactical_model.txt`, `fixture_congestion_note.txt` | Lambda `EvaluateRightBackFit` | `test_right_back_fit.py` | Implemented (local) |
| Right-footed preferred | `coach_tactical_model.txt` | Lambda `EvaluateRightBackFit` | Unit tests | Implemented (local) |
| Build-up, crossing, overlapping runs | `coach_tactical_model.txt` | Lambda `EvaluateRightBackFit` | Unit tests | Implemented (local) |
| Salary must fit budget (RB) | `transfer_budget.txt` | Lambda `EvaluateRightBackFit` | Unit tests | Implemented (local) |
| Below striker position AM/SS | `coach_tactical_model.txt`, `winter_window_priorities.txt` | Lambda `EvaluateBelowStrikerFit` | `test_below_striker_fit.py` | Implemented (local) |
| Vision/creativity/key passing ≥ 8 | `coach_tactical_model.txt` | Lambda `EvaluateBelowStrikerFit` | Boundary test score 8 | Implemented (local) |
| Forward link-up and movement | `coach_tactical_model.txt` | Lambda `EvaluateForwardFit` | `test_forward_fit.py` | Implemented (local) |
| Forward salary ≤ 50,000 unless exception | `coach_tactical_model.txt`, `winter_window_priorities.txt` | Lambda `EvaluateForwardFit` | `test_forward_needs_exception` | Implemented (local) |
| Combined budget respected (forward) | `transfer_budget.txt` | Lambda `EvaluateForwardFit` | Unit tests | Implemented (local) |
| Recommend only with document support | `recruitment_policy.txt` | Agent instruction + KB | Agent prompt #4–6 | AWS pending validation |
| Missing information stated clearly | `recruitment_policy.txt` | Agent instruction | Agent prompt #7 | AWS pending validation |
| No unrelated uploads as evidence | `recruitment_policy.txt` | Agent instruction | Manual / agent test | AWS pending validation |
| Block credential / system-change requests | Task guardrail spec | `scoutmatch-guardrail-user5-avidan` | Prompts #9–10 | AWS pending validation |
| KB: knowledge-base-user5 / scoutmatch prefix | AWS inventory | Agent KB association | `audit_aws_resources.py` | Verified read-only |
| One agent, four action groups, four Lambdas | Task architecture | `deploy_scoutmatch_extension.py` | Deploy plan | Implemented (local) |
| Flow: Input → Agent → Output | Task architecture | `deploy_scoutmatch_extension.py` | Flow validation | AWS pending |
| v14 `/api/sessions/.../messages` unchanged | `app.py` | No edits to chat handler | Existing pytest suite | Preserved |
| Optional `/api/recruitment-flow/chat` | Task Phase 13 | `bedrock_flow_service.py`, `app.py` | `test_bedrock_flow_extension.py` | Implemented (local) |

## Course guideline document

`bedrock_kb_flask_project_guideline.docx` was **not found** in this repository. It was not committed. Use lecturer-provided copy locally as reference only.
