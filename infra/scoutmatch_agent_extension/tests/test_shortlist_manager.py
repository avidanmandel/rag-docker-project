import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
_LAMBDA = Path(__file__).resolve().parents[1] / "lambdas" / "shortlist_manager"
_COMMON = _LAMBDA.parent / "common"
for path in (str(_COMMON), str(_LAMBDA)):
    if path not in sys.path:
        sys.path.insert(0, path)
_spec = importlib.util.spec_from_file_location(
    "scoutmatch_shortlist_lambda", _LAMBDA / "lambda_function.py"
)
shortlist = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(shortlist)


def _body(resp):
    return json.loads(resp["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def _event(function, params, confirmed=False):
    attrs = {"write_confirmed": "true"} if confirmed else {}
    return {
        "function": function,
        "parameters": [{"name": k, "value": str(v)} for k, v in params.items()],
        "sessionAttributes": attrs,
    }


@pytest.fixture(autouse=True)
def clear_store():
    shortlist._LOCAL_STORE.clear()
    yield
    shortlist._LOCAL_STORE.clear()


def test_add_requires_confirmation():
    resp = shortlist.lambda_handler(
        _event(
            "AddCandidateToShortlist",
            {
                "candidate_name": "Ron Ben Ari",
                "target_role": "right-back",
                "status": "shortlisted",
            },
        ),
        None,
    )
    assert _body(resp)["status"] == "PENDING_CONFIRMATION"


def test_add_list_update_remove():
    shortlist.lambda_handler(
        _event(
            "AddCandidateToShortlist",
            {
                "candidate_name": "Ron Ben Ari",
                "target_role": "right-back",
                "status": "shortlisted",
                "recruitment_note": "Strong overlap",
            },
            confirmed=True,
        ),
        None,
    )
    listed = _body(
        shortlist.lambda_handler(_event("ListShortlistCandidates", {}), None)
    )
    assert listed["count"] == 1
    updated = _body(
        shortlist.lambda_handler(
            _event(
                "UpdateCandidateShortlistStatus",
                {"candidate_name": "Ron Ben Ari", "status": "approved"},
                confirmed=True,
            ),
            None,
        )
    )
    assert updated["status"] == "UPDATED"
    removed = _body(
        shortlist.lambda_handler(
            _event("RemoveCandidateFromShortlist", {"candidate_name": "Ron Ben Ari"}, confirmed=True),
            None,
        )
    )
    assert removed["status"] == "REMOVED"


def test_no_cv_or_secrets_stored():
    shortlist.lambda_handler(
        _event(
            "AddCandidateToShortlist",
            {
                "candidate_name": "Example",
                "target_role": "forward",
                "status": "review",
                "recruitment_note": "safe note only",
            },
            confirmed=True,
        ),
        None,
    )
    item = next(iter(shortlist._LOCAL_STORE.values()))
    blob = json.dumps(item)
    assert "BEGIN PRIVATE KEY" not in blob
    assert "raw_cv" not in blob.lower()
