# ScoutMatch Agent + Flow Screenshot Checklist

Save PNGs under `submission_evidence/agent_flow_extension/`. Do not overwrite `submission_evidence/final_v14/`.

| File | What it proves |
|------|----------------|
| 01_new_agent_overview.png | New agent `scoutmatch-recruitment-agent-user5-avidan` exists |
| 02_agent_four_action_groups.png | Four ScoutMatch*ActionsAvidan groups are attached |
| 03_agent_knowledge_base_attached.png | `knowledge-base-user5` is associated |
| 04_agent_guardrail_attached.png | `scoutmatch-guardrail-user5-avidan` on agent only |
| 05_guardrail_version_1.png | Guardrail version 1 published |
| 06_four_lambdas_filtered_list.png | Four new ScoutMatch*Avidan Lambdas in console |
| 07_lambda_scoped_permission_example.png | bedrock.amazonaws.com invoke with SourceArn scoped to agent |
| 08_agent_budget_test_success.png | Budget PASS example (58k + 35k committed) |
| 09_agent_right_back_test_success.png | Ron Ben Ari / right-back evaluation |
| 10_agent_below_striker_test_success.png | Tal Raz / below-striker evaluation |
| 11_agent_forward_test_success.png | Or David / forward policy evaluation |
| 12_agent_missing_information_refusal.png | Unknown player — missing facts, no invention |
| 13_guardrail_credentials_blocked.png | Credentials prompt blocked |
| 14_guardrail_prompt_attack_blocked.png | Prompt attack blocked |
| 15_flow_three_nodes.png | Input → Agent → Output flow graph |
| 16_flow_successful_invocation.png | Flow test invocation succeeded |
| 17_existing_v14_flask_ui_unchanged.png | Production/local v14 UI unchanged |
| 18_native_action_group.png | ScoutMatchNativeActionsAvidan on agent (quota-safe consolidated group) |
| 19_native_lambdas_list.png | ScoutMatchNativeToolsAvidan + standalone native Lambdas |
| 20_native_write_confirmation.png | Bedrock requireConfirmation on write functions |
| 21_dynamodb_shortlist_table.png | ScoutMatchRecruitmentShortlistAvidan table |
| 22_dynamodb_reviews_table.png | ScoutMatchRecruitmentReviewsAvidan table |
| 23_step_functions_graph.png | ScoutMatchCandidateReviewWorkflowAvidan graph |
| 24_step_functions_success.png | Successful Standard workflow execution |
| 25_chat_shortlist_confirmation.png | Shortlist write confirmation in advisor chat |
| 26_chat_shortlist_saved.png | Shortlist saved result in chat |
| 27_chat_budget_followup_same_session.png | Budget follow-up in same advisor session |
| 28_chat_workflow_result.png | Full review workflow result in chat |
| 29_chat_recruitment_brief.png | Generated recruitment brief in chat |
| 30_four_football_action_groups.png | Existing four deterministic Action Groups still attached |
