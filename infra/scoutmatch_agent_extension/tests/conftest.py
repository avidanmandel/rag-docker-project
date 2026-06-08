"""Isolate shared_football vs football_operations modules polluted at collection time."""

from __future__ import annotations

import pytest

from lambda_test_isolation import CONFLICTING_MODULES, evict_conflicting_modules


def _evict_conflicting_modules() -> None:
    evict_conflicting_modules()


def pytest_configure(config):  # noqa: ARG001
    _evict_conflicting_modules()


def pytest_sessionstart(session):  # noqa: ARG001
    _evict_conflicting_modules()


@pytest.fixture(autouse=True)
def _isolate_lambda_module_cache():
    _evict_conflicting_modules()
    yield
    _evict_conflicting_modules()
