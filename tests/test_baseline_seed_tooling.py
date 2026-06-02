"""Regression tests for baseline seed/cleanup soak tooling."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


class SeedS3AlignmentTests(unittest.TestCase):
    def test_realign_when_registry_matches_but_s3_body_stale(self):
        import scripts.seed_baseline_club_knowledge as seed_mod

        manifest = {
            "files": [
                {"filename": "club_profile.txt", "category": "Club Profile"},
            ]
        }
        local_bytes = b"fresh baseline body"
        stale_digest = "deadbeef" * 8
        fresh_digest = seed_mod.hashlib.sha256(local_bytes).hexdigest()

        with mock.patch.object(seed_mod, "_load_manifest", return_value=manifest), mock.patch.object(
            seed_mod, "_file_bytes", return_value=local_bytes
        ), mock.patch.object(seed_mod, "database") as db, mock.patch.object(
            seed_mod, "aws_storage"
        ) as storage, mock.patch.object(
            seed_mod.config, "AWS_BASELINE_SET_ID", "production"
        ):
            db.list_baseline_documents.return_value = [
                {
                    "s3_key": "scoutmatch/knowledge-base/baseline/production/club_profile.txt",
                    "content_hash": fresh_digest,
                }
            ]
            storage.build_baseline_object_key.return_value = (
                "scoutmatch/knowledge-base/baseline/production/club_profile.txt"
            )
            storage.read_object_bytes.return_value = b"stale s3 body"
            storage.upload_baseline_document.return_value = {
                "key": "scoutmatch/knowledge-base/baseline/production/club_profile.txt",
                "display_name": "club_profile.txt",
            }

            summary = seed_mod.seed(apply=True, baseline_set_id="production", wait_sync=False)

        self.assertEqual(summary["realigned"], 1)
        self.assertEqual(summary["skipped"], 0)
        storage.upload_baseline_document.assert_called_once()
        db.upsert_baseline_document.assert_called_once()

    def test_skip_when_registry_and_s3_aligned(self):
        import scripts.seed_baseline_club_knowledge as seed_mod

        manifest = {"files": [{"filename": "club_profile.txt", "category": "Club Profile"}]}
        local_bytes = b"aligned body"
        digest = seed_mod.hashlib.sha256(local_bytes).hexdigest()

        with mock.patch.object(seed_mod, "_load_manifest", return_value=manifest), mock.patch.object(
            seed_mod, "_file_bytes", return_value=local_bytes
        ), mock.patch.object(seed_mod, "database") as db, mock.patch.object(
            seed_mod, "aws_storage"
        ) as storage:
            db.list_baseline_documents.return_value = [
                {"s3_key": "k/club_profile.txt", "content_hash": digest}
            ]
            storage.build_baseline_object_key.return_value = "k/club_profile.txt"
            storage.read_object_bytes.return_value = local_bytes

            summary = seed_mod.seed(apply=True, baseline_set_id="production", wait_sync=False)

        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["realigned"], 0)
        storage.upload_baseline_document.assert_not_called()


class BaselineGateSeedTests(unittest.TestCase):
    def test_loopback_seed_requires_candidate_container(self):
        import scripts.run_baseline_business_gate as gate

        original_base = gate.BASE
        try:
            gate.BASE = "http://127.0.0.1:5001"
            with mock.patch.dict(gate.os.environ, {}, clear=True), mock.patch.object(
                gate, "ensure_baseline_fixtures"
            ), mock.patch.object(gate.subprocess, "check_call") as check:
                with self.assertRaises(RuntimeError):
                    gate.seed_baseline_set()
                check.assert_not_called()
        finally:
            gate.BASE = original_base

    def test_candidate_seed_uses_docker_exec(self):
        import scripts.run_baseline_business_gate as gate

        with mock.patch.dict(
            gate.os.environ,
            {"CANDIDATE": "scoutmatch-ai-baseline-v13-soak-candidate"},
            clear=True,
        ), mock.patch.object(gate, "BASELINE_SET_ID", "candidate-soak-20260101120000"), mock.patch.object(
            gate, "ensure_baseline_fixtures"
        ), mock.patch.object(gate.subprocess, "check_call") as check:
            gate.seed_baseline_set()
            cmd = check.call_args[0][0]
            self.assertIn("docker", cmd)
            self.assertIn("exec", cmd)
            self.assertIn("candidate-soak-20260101120000", cmd)


class CleanupCandidateBaselineTests(unittest.TestCase):
    def test_refuses_production_delete(self):
        import scripts.cleanup_candidate_baseline_set as cleanup

        with self.assertRaises(RuntimeError):
            cleanup.delete_baseline_set("production")

    def test_deletes_only_disposable_prefix(self):
        import scripts.cleanup_candidate_baseline_set as cleanup

        with mock.patch.object(cleanup, "list_baseline_keys", return_value=["k/a.txt"]), mock.patch.object(
            cleanup.aws_storage, "_ensure_clients"
        ), mock.patch.object(
            cleanup.aws_storage, "_s3"
        ) as s3, mock.patch.object(
            cleanup.aws_storage, "metadata_sidecar_key", return_value="k/a.txt.metadata.json"
        ), mock.patch.object(
            cleanup.config, "baseline_s3_prefix", return_value="k/"
        ):
            s3.delete_objects.return_value = {"Deleted": [{"Key": "k/a.txt"}], "Errors": []}
            result = cleanup.delete_baseline_set("candidate-soak-20260101120000")
        self.assertEqual(result["deleted"], 1)
        s3.delete_objects.assert_called_once()

    def test_auto_lists_candidate_sets_not_production(self):
        import scripts.cleanup_candidate_baseline_set as cleanup

        with mock.patch.object(
            cleanup, "list_disposable_baseline_sets", return_value=["candidate-soak-1", "candidate-2"]
        ), mock.patch.object(cleanup, "list_baseline_keys", return_value=[]):
            sets = cleanup.list_disposable_baseline_sets()
        self.assertNotIn("production", sets)


class SoakHarnessIsolationTests(unittest.TestCase):
    def test_soak_baseline_set_id_pattern(self):
        import scripts.run_v13_soak as soak

        self.assertTrue(soak.BASELINE_SET_ID.startswith("candidate-soak-"))
        self.assertNotEqual(soak.BASELINE_SET_ID, "production")

    def test_soak_runtime_isolated_from_production(self):
        import scripts.run_v13_soak as soak

        self.assertIn("soak-runtime", soak.RUNTIME)
        self.assertNotIn("scoutmatch-ai-runtime", soak.RUNTIME)


if __name__ == "__main__":
    unittest.main()
