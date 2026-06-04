"""
ScoutMatchNativeToolsAvidan — single action group router (Bedrock 10-API quota).

Exposes six agent-attached functions; additional helpers remain available for direct Lambda tests.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_LAMBDA_ROOT = Path(__file__).resolve().parent
_LAMBDAS = _LAMBDA_ROOT.parent
_COMMON = _LAMBDAS / "common"
if str(_COMMON) not in sys.path:
    sys.path.insert(0, str(_COMMON))


def _load_module(name: str, relative: str):
    path = _LAMBDAS / relative / "lambda_function.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_shortlist = _load_module("scoutmatch_shortlist", "shortlist_manager")
_brief = _load_module("scoutmatch_brief", "recruitment_brief")
_workflow = _load_module("scoutmatch_workflow", "recruitment_workflow")

_AGENT_FUNCTIONS = {
    "AddCandidateToShortlist": _shortlist,
    "ListShortlistCandidates": _shortlist,
    "RemoveCandidateFromShortlist": _shortlist,
    "CreateRecruitmentBrief": _brief,
    "GetRecruitmentBrief": _brief,
    "StartCandidateReviewWorkflow": _workflow,
}


def lambda_handler(event, context):  # noqa: ARG001
    function_name = (event.get("function") or "").strip()
    module = _AGENT_FUNCTIONS.get(function_name)
    if not module:
        return _shortlist.build_function_response(
            action_group=event.get("actionGroup", "ScoutMatchNativeActionsAvidan"),
            function_name=function_name or "Unknown",
            body={"status": "FAILURE", "message": "Unknown native tool function."},
            event=event,
        )
    return module.lambda_handler(event, context)
