"""Clear dual-path Lambda module cache polluted during full-suite collection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INFRA_TESTS = ROOT / "infra" / "scoutmatch_agent_extension" / "tests"
if str(INFRA_TESTS) not in sys.path:
    sys.path.insert(0, str(INFRA_TESTS))

ISOLATION = INFRA_TESTS / "lambda_test_isolation.py"
_spec = __import__("importlib.util", fromlist=["spec_from_file_location"]).spec_from_file_location(
    "lambda_test_isolation_root", ISOLATION
)
_isolation = __import__("importlib.util", fromlist=["module_from_spec"]).module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_isolation)
evict_conflicting_modules = _isolation.evict_conflicting_modules


def pytest_configure(config):  # noqa: ARG001
    evict_conflicting_modules()


@pytest.fixture(autouse=True)
def _evict_lambda_module_cache_after_root_test():
    yield
    evict_conflicting_modules()
