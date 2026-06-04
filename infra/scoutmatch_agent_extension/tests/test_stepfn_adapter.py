from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lambdas" / "common"))

from stepfn_adapter import bedrock_action_event, parse_function_body, sanitize_workflow_reference  # noqa: E402


def test_bedrock_action_event_shape():
    event = bedrock_action_event(
        action_group="ScoutMatchBudgetActionsAvidan",
        function_name="CalculateBudgetImpact",
        parameters={"candidate_name": "Example", "candidate_annual_salary_eur": 58000},
    )
    assert event["actionGroup"] == "ScoutMatchBudgetActionsAvidan"
    assert event["function"] == "CalculateBudgetImpact"
    names = {p["name"] for p in event["parameters"]}
    assert "candidate_name" in names


def test_parse_function_body():
    payload = {
        "response": {
            "functionResponse": {
                "responseBody": {"TEXT": {"body": '{"decision":"PASS"}'}}
            }
        }
    }
    assert parse_function_body(payload)["decision"] == "PASS"


def test_sanitize_workflow_reference():
    ref = sanitize_workflow_reference("arn:aws:states:us-east-1:123456789012:execution:demo:abc")
    assert ref.startswith("review-")
    assert "arn:aws" not in ref
