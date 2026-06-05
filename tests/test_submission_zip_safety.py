"""Regression tests for submission ZIP exclusion and forbidden-entry validation."""

from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "scripts" / "submission_zip_rules.py"
PREPARE = ROOT / "scripts" / "prepare_submission_zip.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_local_directory_excluded_from_package():
    rules = _load_module(RULES, "submission_zip_rules")
    sample = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
    if sample.parent.exists():
        assert rules.should_include(sample, root=ROOT) is False


def test_repair_helpers_excluded_from_package():
    rules = _load_module(RULES, "submission_zip_rules")
    for name in ("fix_agent_model.py", "repair_agent_runtime.py"):
        path = ROOT / "infra" / "scoutmatch_agent_extension" / "scripts" / name
        if path.exists():
            assert rules.should_include(path, root=ROOT) is False


def test_env_agent_excluded_but_examples_allowed():
    rules = _load_module(RULES, "submission_zip_rules")
    assert rules.should_include(ROOT / ".env.agent", root=ROOT) is False
    example = ROOT / ".env.example"
    if example.exists():
        assert rules.should_include(example, root=ROOT) is True


def test_forbidden_zip_entry_detection():
    rules = _load_module(RULES, "submission_zip_rules")
    hits = rules.find_forbidden_zip_entries(
        [
            "infra/scoutmatch_agent_extension/.local/state.json",
            "chat.db",
            "keys/deploy.pem",
            "infra/scoutmatch_agent_extension/scripts/repair_agent_runtime.py",
            "README.md",
        ]
    )
    assert "README.md" not in hits
    assert any(".local" in h for h in hits)
    assert any(h.endswith("chat.db") for h in hits)
    assert any(h.endswith(".pem") for h in hits)
    assert any("repair_agent_runtime.py" in h for h in hits)


def test_generated_submission_zip_has_no_forbidden_entries():
    prepare = _load_module(PREPARE, "prepare_submission_zip")
    rules = _load_module(RULES, "submission_zip_rules")
    exit_code = prepare.build_submission_zip()
    assert exit_code == 0
    zip_path = ROOT / "dist" / "Avidan_RAG_Docker_Project-submission.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        forbidden = rules.find_forbidden_zip_entries(zf.namelist())
    assert forbidden == []
    manifest_doc = ROOT / "docs" / "SCOUTMATCH_SUBMISSION_ZIP_MANIFEST.md"
    assert manifest_doc.exists()
    assert "READY_FOR_MANUAL_SCREENSHOTS" in manifest_doc.read_text(encoding="utf-8")
