"""
ScoutMatch AI automated tests (mocked AWS where possible).

Run: python -m pytest tests/test_scoutmatch.py -v
Or:  python tests/test_scoutmatch.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("RAG_BACKEND", "aws_kb")
os.environ.setdefault("BEDROCK_KB_ID", "TEST_KB")
os.environ.setdefault("BEDROCK_DATA_SOURCE_ID", "TEST_DS")
os.environ.setdefault("BEDROCK_MODEL_ARN", "arn:aws:bedrock:us-east-1::foundation-model/test")
os.environ.setdefault("AWS_S3_BUCKET", "test-scoutmatch-bucket")
os.environ.setdefault("AWS_S3_PREFIX", "scoutmatch/knowledge-base/")
os.environ.setdefault("AWS_KB_RETRIEVE_CANDIDATES", "30")
os.environ.setdefault("AWS_KB_CONTEXT_SOURCE_LIMIT", "10")
os.environ.setdefault("AWS_KB_MAX_CHUNKS_PER_SOURCE", "2")

import config  # noqa: E402
import database  # noqa: E402
from aws_kb_engine import (  # noqa: E402
    AWSKnowledgeBaseEngine,
    EXPLICIT_GENERATION_PROMPT,
    _NAME_RETRY_INSTRUCTION,
    _build_bedrock_prompt_template,
    _build_explicit_generation_system_prompt,
    _build_generation_user_message,
    _chunks_are_near_duplicate,
    _canonical_source_key,
    _filter_scoutmatch_results,
    _is_allowed_session_source,
    _is_allowed_scoutmatch_source,
    _is_comparison_or_recommendation_question,
    _is_named_player_profile_question,
    _is_question_in_scoutmatch_domain,
    _extract_named_player_from_profile_question,
    _expand_named_player_retrieval_query,
    _build_retrieval_queries,
    _contains_hebrew,
    _english_player_name,
    _normalize_hebrew_profile_question_to_english,
    _language_instruction_for_question,
    _select_complete_diverse_context_chunks,
    _select_diverse_context_chunks,
    build_grounded_context_block,
    chunks_to_source_cards,
    extract_sources_from_citations,
    has_internal_markers,
    sanitize_bedrock_answer,
    select_main_source,
    validate_final_answer,
)
from requirement_verification import (  # noqa: E402
    EXACT_MATCH_ACKNOWLEDGMENT_RETRY_INSTRUCTION,
    MATRIX_CONTRADICTION_RETRY_INSTRUCTION,
    build_safe_exact_match_fallback,
    build_verified_candidate_matrix,
    extract_recruitment_requirements,
    extract_verified_player_facts,
    format_verified_matrix_for_prompt,
    get_exact_match_candidates,
    validate_answer_against_verified_matrix,
    validate_exact_match_acknowledgment,
    _parse_facts_from_text,
)
from aws_storage_service import (  # noqa: E402
    AWSStorageService,
    UploadValidationError,
    canonical_display_filename,
    deduplicate_documents_for_display,
)

SCOUT_BUCKET = "test-scoutmatch-bucket"
SCOUT_PREFIX = "scoutmatch/knowledge-base/"
TEST_SESSION_ID = "sessionabc123"
SCOUT_GK_URI = (
    f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/goalkeeper_daniel_cohen.txt"
)

DANIEL_PROFILE = (
    "COMPACT FACT PROFILE SUMMARY\n"
    "Full Name: Daniel Cohen | Position: Goalkeeper (GK) | Professional Experience: 6 years\n"
    "Annual Salary Expectation: 75,000 EUR | Relocation Willingness: YES\n"
    "Build-up Ability: Strong | Calmness Under Pressure: Strong | Preferred Foot: Right"
)
YOSSI_PROFILE = (
    "COMPACT FACT PROFILE SUMMARY\n"
    "Full Name: Yossi Levi | Professional Experience: 9 years\n"
    "Annual Salary Expectation: 65,000 EUR | Relocation Willingness: NO\n"
    "Build-up Ability: Limited | Calmness Under Pressure: Strong"
)
OMER_PROFILE = (
    "COMPACT FACT PROFILE SUMMARY\n"
    "Full Name: Omer Azulay | Professional Experience: 8 years\n"
    "Annual Salary Expectation: 90,000 EUR | Relocation Willingness: MAYBE\n"
    "Build-up Ability: Inconsistent | Calmness Under Pressure: Variable"
)
MARCO_PROFILE = (
    "COMPACT FACT PROFILE SUMMARY\n"
    "Full Name: Marco Silva\n"
    "Position: Goalkeeper (GK)\n"
    "Professional Experience: 7 years\n"
    "Annual Salary Expectation: 78,000 EUR\n"
    "Relocation Willingness: YES — willing to relocate north\n"
    "Build-up Ability: Strong\n"
    "Calmness Under Pressure: Strong"
)

MARCO_NARRATIVE_ONLY = (
    "Full Name: Marco Silva\n"
    "Years of Professional Experience: 7\n"
    "Annual Salary Expectation: 78,000 EUR\n"
    "Relocation Willingness: YES\n"
    "Marco Silva is a build-up goalkeeper specialist with composure under high press."
)

OR_DAVID_PROFILE = (
    "Full Name: Or David\n"
    "Position: Striker (ST) / False Nine (CF)\n"
    "Age: 26\n"
    "Years of Professional Experience: 6\n"
    "Current Club: Beitar Jerusalem\n"
    "Annual Salary Expectation: 58,000 EUR\n"
    "Relocation Willingness: MAYBE\n"
    "Preferred Foot: Right"
)

AMIT_LEVY_PROFILE = (
    "Full Name: Amit Levy\n"
    "Position: Centre-Back (CB)\n"
    "Age: 25\n"
    "Years of Professional Experience: 5\n"
    "Current Club: Hapoel Be'er Sheva\n"
    "Annual Salary Expectation: 58,000 EUR\n"
    "Relocation Willingness: YES\n"
    "Preferred Foot: Left"
)


def _aws_doc(name: str, *, category: str = "PLAYER CV", last_modified: str = "") -> dict:
    return {
        "key": f"{SCOUT_PREFIX}player_cvs/{name}",
        "name": f"{SCOUT_PREFIX}player_cvs/{name}",
        "display_name": name,
        "display_source": name,
        "category": category,
        "last_modified": last_modified,
        "size": 100,
    }


def _source_card(filename: str, text: str, score: float) -> dict:
    return {
        "text": text,
        "source": filename,
        "score": score,
        "s3_uri": f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}player_cvs/{filename}",
    }


def _player_chunk(filename: str, text: str) -> dict:
    return {
        "text": text,
        "source": filename,
        "score": 0.9,
        "s3_uri": f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}player_cvs/{filename}",
    }


RECRUITMENT_QUESTION_EN = (
    "Who is the most suitable goalkeeper with at least 5 years of experience, "
    "calm under pressure, good with his feet, willing to relocate north, "
    "and a salary up to 80,000 EUR?"
)

RECRUITMENT_QUESTION_HE = (
    "אני מחפש שוער עם לפחות 5 שנות ניסיון, רגוע תחת לחץ, "
    "טוב במשחק רגל, מוכן לעבור לצפון ושכרו עד 80,000 אירו לעונה. "
    "מי המועמד המתאים ביותר ולמה?"
)


def _dual_exact_match_matrix() -> dict:
    requirements = extract_recruitment_requirements(RECRUITMENT_QUESTION_EN)
    return build_verified_candidate_matrix(
        extract_verified_player_facts([
            _player_chunk("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE),
            _player_chunk("goalkeeper_marco_silva.txt", MARCO_PROFILE),
        ]),
        requirements,
    )


def _dual_player_retrieve_payload() -> dict:
    return {
        "retrievalResults": [
            {
                "content": {"text": DANIEL_PROFILE},
                "score": 0.9,
                "location": {
                    "s3Location": {
                        "uri": (
                            f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
                            "player_cvs/goalkeeper_daniel_cohen.txt"
                        ),
                    },
                },
            },
            {
                "content": {"text": MARCO_PROFILE},
                "score": 0.85,
                "location": {
                    "s3Location": {
                        "uri": (
                            f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
                            "player_cvs/goalkeeper_marco_silva.txt"
                        ),
                    },
                },
            },
        ],
    }

# Isolate tests from a developer's local .env bucket/prefix values.
config.AWS_S3_BUCKET = SCOUT_BUCKET
config.AWS_S3_PREFIX = SCOUT_PREFIX


def _converse_response(text: str) -> dict:
    return {"output": {"message": {"content": [{"text": text}]}}}


def _retrieve_payload(text: str, uri: str = SCOUT_GK_URI, score: float = 0.9) -> dict:
    return {
        "retrievalResults": [{
            "content": {"text": text},
            "score": score,
            "location": {"s3Location": {"uri": uri}},
        }]
    }


def _prepare_engine_with_mocks(engine: AWSKnowledgeBaseEngine) -> None:
    engine.ready = True
    engine._runtime_client = MagicMock()
    engine._bedrock_client = MagicMock()
    raw_answer = engine.answer

    def answer_with_session(question, *args, **kwargs):
        _rewrite_mock_retrieve_uris_for_session(engine._runtime_client.retrieve.return_value)
        kwargs.setdefault("app_session_id", TEST_SESSION_ID)
        return raw_answer(question, *args, **kwargs)

    engine.answer = answer_with_session


def _rewrite_mock_retrieve_uris_for_session(payload: object) -> None:
    if not isinstance(payload, dict):
        return
    base = f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
    session_base = f"{base}sessions/{TEST_SESSION_ID}/"
    for item in payload.get("retrievalResults") or []:
        location = item.get("location") or {}
        s3 = location.get("s3Location") or location.get("s3_location") or {}
        uri = s3.get("uri")
        if (
            isinstance(uri, str)
            and uri.startswith(base)
            and f"{SCOUT_PREFIX}sessions/" not in uri
            and f"{SCOUT_PREFIX}data/" not in uri
            and "/data/" not in uri
        ):
            s3["uri"] = session_base + Path(uri).name


class StrictRAGTests(unittest.TestCase):
    def setUp(self):
        self.engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(self.engine)

    def test_refusal_no_relevant_documents(self):
        self.engine._runtime_client.retrieve.return_value = {"retrievalResults": []}
        result = self.engine.answer("Which player played in Japan?")
        self.assertTrue(result["refused"])
        self.engine._bedrock_client.converse.assert_not_called()

    def test_grounded_goalkeeper_answer(self):
        self.engine._runtime_client.retrieve.return_value = _retrieve_payload(
            "Daniel remains calm when pressed. Comfortable receiving back-passes."
        )
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Daniel Cohen appears strongest for build-up play."
        )
        result = self.engine.answer("Which goalkeeper is comfortable receiving back-passes?")
        self.assertFalse(result["refused"])
        self.assertTrue(result["context"])
        self.assertIn("daniel", result["answer"].lower())
        self.engine._runtime_client.retrieve_and_generate.assert_not_called()

    def test_missing_japan_experience_refusal(self):
        self.engine._runtime_client.retrieve.return_value = {"retrievalResults": []}
        result = self.engine.answer("Which player played in Japan?")
        self.assertTrue(result["refused"])


class StrictCitationTests(unittest.TestCase):
    """Explicit retrieve-then-generate pipeline grounding checks."""

    def setUp(self):
        self.engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(self.engine)
        self.scout_text = "Daniel remains calm when pressed under high press."
        self.retrieve_hit = _retrieve_payload(self.scout_text, score=0.82)

    def test_refused_when_only_non_scoutmatch_sources(self):
        self.engine._runtime_client.retrieve.return_value = {
            "retrievalResults": [{
                "content": {"text": "Unrelated course material."},
                "score": 0.95,
                "location": {"s3Location": {"uri": "s3://test-scoutmatch-bucket/data/docker_aws.pdf"}},
            }]
        }
        result = self.engine.answer("Which goalkeeper fits build-up play?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "no_scoutmatch_sources")
        self.engine._bedrock_client.converse.assert_not_called()

    def test_refused_when_generation_empty(self):
        self.engine._runtime_client.retrieve.return_value = self.retrieve_hit
        self.engine._bedrock_client.converse.return_value = _converse_response("   ")
        result = self.engine.answer("Which goalkeeper fits build-up play?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "model_refusal")

    def test_accepted_when_valid_retrieve_and_generation(self):
        self.engine._runtime_client.retrieve.return_value = self.retrieve_hit
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Daniel Cohen appears strongest."
        )
        result = self.engine.answer("Which goalkeeper is comfortable receiving back-passes?")
        self.assertFalse(result["refused"])
        self.assertTrue(result["context"])
        self.assertIn("daniel", result["answer"].lower())
        self.assertEqual(result["context"][0]["source"], "goalkeeper_daniel_cohen.txt")

    def test_hebrew_unrelated_question_strict_refusal(self):
        result = self.engine.answer("מי זה דונלד טראמפ?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_HE)
        self.assertEqual(result["reason"], "out_of_domain")
        self.engine._runtime_client.retrieve.assert_not_called()
        self.engine._bedrock_client.converse.assert_not_called()

    def test_production_path_does_not_use_retrieve_and_generate(self):
        self.engine._runtime_client.retrieve.return_value = self.retrieve_hit
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Daniel Cohen is recommended."
        )
        self.engine.answer("Which goalkeeper fits build-up play?")
        self.engine._runtime_client.retrieve_and_generate.assert_not_called()
        self.engine._bedrock_client.converse.assert_called_once()


class AnswerQualityTests(unittest.TestCase):
    """Prompt quality, marker cleanup, and answer sanitization."""

    def test_sanitize_removes_passage_markers(self):
        raw = "The recommended candidate is highlighted in Passage %[4]%."
        cleaned = sanitize_bedrock_answer(raw)
        self.assertNotIn("Passage", cleaned)
        self.assertNotIn("%[4]%", cleaned)
        self.assertIn("recommended candidate", cleaned.lower())

    def test_sanitize_preserves_normal_percentages(self):
        raw = "Salary up to 80% of the budget and 30 percent relocation bonus."
        cleaned = sanitize_bedrock_answer(raw)
        self.assertIn("80%", cleaned)
        self.assertIn("30 percent", cleaned)

    def test_hebrew_question_prompt_includes_hebrew_language_instruction(self):
        prompt = _build_explicit_generation_system_prompt("מי השוער המתאים ביותר?")
        self.assertIn("Hebrew", prompt)
        self.assertIn("same language", EXPLICIT_GENERATION_PROMPT)

    def test_english_question_prompt_includes_english_language_instruction(self):
        instruction = _language_instruction_for_question("Which goalkeeper fits best?")
        self.assertIn("English", instruction)

    def test_prompt_includes_numeric_consistency_instruction(self):
        prompt = EXPLICIT_GENERATION_PROMPT.lower()
        self.assertIn("never claim that 4 years satisfies", prompt)
        self.assertIn("5 years", prompt)

    def test_prompt_includes_no_exact_match_instruction(self):
        prompt = EXPLICIT_GENERATION_PROMPT
        self.assertIn("לא נמצא מועמד שעומד בכל דרישות החובה", prompt)
        self.assertIn("list every unmet requirement", prompt.lower())

    def test_engine_sanitizes_markers_in_live_answer_path(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _retrieve_payload(
            "Marco Silva excels at build-up play.",
            uri=(
                f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
                "player_cvs/goalkeeper_marco_silva.txt"
            ),
            score=0.9,
        )
        engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Marco Silva is recommended "
            "as noted in Passage %[4]%."
        )
        result = engine.answer("Which goalkeeper is best for build-up play?")
        self.assertFalse(result["refused"])
        self.assertNotIn("Passage", result["answer"])
        self.assertNotIn("%[4]%", result["answer"])
        self.assertIn("Marco Silva", result["answer"])
        self.assertEqual(result["context"][0]["source"], "goalkeeper_marco_silva.txt")


class RuntimeSafetyTests(unittest.TestCase):
    """Engine and API path runtime quality checks."""

    LIVE_PASSAGE_TEXT = (
        "Based on the uploaded documents, the most suitable candidate for the "
        "goalkeeper position appears to be the one highlighted in Passage %[4]%. "
        "Here are the reasons why this candidate matches the requirements:"
    )

    def setUp(self):
        self.engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(self.engine)
        self.retrieve_hit = _retrieve_payload(
            "Full Name: Daniel Cohen\n"
            "Years of Professional Experience: 6\n"
            "Relocation Willingness: YES",
            score=0.9,
        )

    def test_exact_live_marker_cleanup_via_engine(self):
        self.engine._runtime_client.retrieve.return_value = self.retrieve_hit
        self.engine._bedrock_client.converse.return_value = _converse_response(
            self.LIVE_PASSAGE_TEXT
        )
        question = (
            "I am looking for a goalkeeper with at least 5 years of experience. "
            "Who is the most suitable candidate and why?"
        )
        result = self.engine.answer(question)
        self.assertNotIn("Passage", result["answer"])
        self.assertNotIn("%[4]%", result["answer"])
        self.assertTrue(result["refused"])
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_EN)

    def test_standalone_marker_cleanup_via_engine(self):
        self.engine._runtime_client.retrieve.return_value = self.retrieve_hit
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Daniel Cohen is noted in %[12]% "
            "for build-up play."
        )
        result = self.engine.answer("Which goalkeeper fits build-up play?")
        self.assertNotIn("%[12]%", result["answer"])
        self.assertIn("Daniel Cohen", result["answer"])
        self.assertFalse(result["refused"])

    def test_normal_percentage_preserved_via_engine(self):
        self.engine._runtime_client.retrieve.return_value = self.retrieve_hit
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Daniel Cohen's salary is "
            "within an 80% threshold."
        )
        result = self.engine.answer("Which goalkeeper fits the budget?")
        self.assertIn("80%", result["answer"])
        self.assertFalse(result["refused"])

    def test_runtime_rejection_when_marker_remnant_survives(self):
        self.engine._runtime_client.retrieve.return_value = self.retrieve_hit
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Daniel Cohen is noted in "
            "Passage %[4]% for build-up play."
        )
        question = "Who is the most suitable goalkeeper?"
        with patch(
            "aws_kb_engine.sanitize_bedrock_answer",
            side_effect=lambda text: text,
        ):
            result = self.engine.answer(question)
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "internal_markers")

    def test_reject_vague_recommendation_without_player_name(self):
        self.engine._runtime_client.retrieve.return_value = self.retrieve_hit
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, the candidate appears suitable "
            "for the goalkeeper role."
        )
        question = "Who is the most suitable candidate?"
        result = self.engine.answer(question)
        self.assertTrue(result["refused"])
        self.assertIn(result["reason"], ("no_explicit_name", "vague_recommendation"))

    def test_accept_grounded_recommendation_with_explicit_name(self):
        marco_uri = (
            f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
            "demo_upload_later/goalkeeper_marco_silva.txt"
        )
        self.engine._runtime_client.retrieve.return_value = _retrieve_payload(
            "Full Name: Marco Silva\n"
            "Years of Professional Experience: 7\n"
            "Relocation Willingness: YES",
            uri=marco_uri,
            score=0.95,
        )
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Marco Silva is the strongest "
            "match with 7 years of professional experience and willingness "
            "to relocate north."
        )
        question = (
            "Who is the most suitable goalkeeper with at least 5 years experience?"
        )
        result = self.engine.answer(question)
        self.assertFalse(result["refused"])
        self.assertIn("Marco Silva", result["answer"])
        self.assertTrue(result["context"])

    def test_reject_numeric_contradiction(self):
        self.engine._runtime_client.retrieve.return_value = self.retrieve_hit
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, the candidate has a minimum "
            "of 4 years of professional experience, which meets the "
            "requirement of at least 5 years."
        )
        question = "Which goalkeeper has at least 5 years of experience?"
        result = self.engine.answer(question)
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "numeric_contradiction")

    def test_sanitize_exact_live_input_removes_passage_marker(self):
        cleaned = sanitize_bedrock_answer(self.LIVE_PASSAGE_TEXT)
        self.assertNotIn("Passage", cleaned)
        self.assertNotIn("%[4]%", cleaned)

    def test_dataset_neutrality_scan(self):
        biased_phrases = (
            "TOP RECOMMENDATION",
            "Should rank",
            "Always recommend",
            "Choose this player",
            "Best candidate",
            "Rank first",
            "PERFECT MATCH",
            "Strong recommendation",
            "Not recommended for",
        )
        root = PROJECT_ROOT / "sample_scout_data"
        for path in sorted(root.rglob("*.txt")):
            text = path.read_text(encoding="utf-8")
            for phrase in biased_phrases:
                self.assertNotIn(
                    phrase,
                    text,
                    msg=f"{path.relative_to(PROJECT_ROOT)} contains '{phrase}'",
                )

    def test_citation_enforcement_still_refuses_without_sources(self):
        self.engine._runtime_client.retrieve.return_value = {
            "retrievalResults": [{
                "content": {"text": "Stale test data."},
                "score": 0.99,
                "location": {
                    "s3Location": {
                        "uri": f"s3://{SCOUT_BUCKET}/old-tests/knowledge_test.txt",
                    },
                },
            }]
        }
        result = self.engine.answer("Who is the most suitable goalkeeper?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "no_scoutmatch_sources")

    def test_api_message_path_returns_sanitized_refusal(self):
        import app as flask_app

        flask_app.app.config["TESTING"] = True
        client = flask_app.app.test_client()
        session = database.create_session()

        with patch.object(flask_app.engine, "ready", True), patch.object(
            flask_app,
            "_init_error",
            None,
        ), patch.object(
            flask_app.engine,
            "answer",
            return_value={
                "answer": config.REFUSAL_TEXT_EN,
                "context": [],
                "refused": True,
                "reason": "internal_markers",
                "generation_mode": "aws_kb",
            },
        ):
            resp = client.post(
                f"/api/sessions/{session['id']}/messages",
                json={"content": "Who is the most suitable goalkeeper?"},
            )
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["refused"])
        self.assertNotIn("Passage", payload["assistant_message"]["content"])
        self.assertNotIn("%[4]%", payload["assistant_message"]["content"])


class ExplicitRAGTests(unittest.TestCase):
    """Source isolation, context builder, and explicit pipeline tests."""

    def test_allowed_scoutmatch_uri(self):
        uri = (
            f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
            "player_cvs/goalkeeper_daniel_cohen.txt"
        )
        self.assertTrue(_is_allowed_scoutmatch_source(uri))

    def test_reject_old_course_uri(self):
        self.assertFalse(
            _is_allowed_scoutmatch_source(f"s3://{SCOUT_BUCKET}/data/docker_aws.pdf")
        )

    def test_reject_stale_test_uri(self):
        self.assertFalse(
            _is_allowed_scoutmatch_source(
                f"s3://{SCOUT_BUCKET}/old-tests/knowledge_test.txt"
            )
        )

    def test_reject_missing_uri(self):
        self.assertFalse(_is_allowed_scoutmatch_source(None))
        self.assertFalse(_is_allowed_scoutmatch_source(""))

    def test_mixed_results_only_scoutmatch_reaches_context(self):
        mixed = [
            {
                "text": "Daniel Cohen build-up specialist.",
                "score": 0.9,
                "s3_uri": SCOUT_GK_URI,
                "source": "goalkeeper_daniel_cohen.txt",
            },
            {
                "text": "Old docker lecture.",
                "score": 0.95,
                "s3_uri": f"s3://{SCOUT_BUCKET}/data/docker_aws.pdf",
                "source": "docker_aws.pdf",
            },
            {
                "text": "Stale test chunk.",
                "score": 0.99,
                "s3_uri": f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}knowledge_test.txt",
                "source": "knowledge_test.txt",
            },
        ]
        kept = _filter_scoutmatch_results(mixed, min_score=None, top_k=5)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["source"], "goalkeeper_daniel_cohen.txt")

    def test_no_valid_scoutmatch_chunks_refusal(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = {
            "retrievalResults": [{
                "content": {"text": "Unrelated"},
                "score": 0.99,
                "location": {
                    "s3Location": {"uri": f"s3://{SCOUT_BUCKET}/data/for_check.txt"},
                },
            }]
        }
        result = engine.answer("Which goalkeeper fits?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "no_scoutmatch_sources")

    def test_context_builder_includes_filename_and_text(self):
        block = build_grounded_context_block([{
            "text": "Full Name: Daniel Cohen",
            "score": 0.88,
            "source": "goalkeeper_daniel_cohen.txt",
            "s3_uri": SCOUT_GK_URI,
        }])
        self.assertIn("goalkeeper_daniel_cohen.txt", block)
        self.assertIn("Daniel Cohen", block)
        self.assertIn("[Source 1]", block)

    def test_hebrew_generation_prompt(self):
        prompt = _build_explicit_generation_system_prompt("מי השוער המתאים?")
        self.assertIn("Hebrew", prompt)

    def test_english_generation_prompt(self):
        prompt = _build_explicit_generation_system_prompt("Which goalkeeper fits?")
        self.assertIn("English", prompt)

    def test_source_cards_from_retrieve_only(self):
        cards = chunks_to_source_cards([{
            "text": "Salary expectation: 75000 EUR",
            "score": 0.7,
            "source": "goalkeeper_daniel_cohen.txt",
            "s3_uri": SCOUT_GK_URI,
        }])
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["source"], "goalkeeper_daniel_cohen.txt")
        self.assertEqual(cards[0]["category"], "PLAYER CV")

    def test_source_card_isolation_excludes_course_doc(self):
        cards = chunks_to_source_cards([{
            "text": "Course notes",
            "score": 0.9,
            "source": "docker_aws.pdf",
            "s3_uri": f"s3://{SCOUT_BUCKET}/data/docker_aws.pdf",
        }])
        self.assertEqual(cards, [])
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = {
            "retrievalResults": [{
                "content": {"text": "Course notes"},
                "score": 0.9,
                "location": {"s3Location": {"uri": f"s3://{SCOUT_BUCKET}/data/docker_aws.pdf"}},
            }]
        }
        result = engine.answer("Which goalkeeper fits?")
        self.assertTrue(result["refused"])

    def test_follow_up_includes_recent_chat(self):
        msg = _build_generation_user_message(
            "What salary does he expect?",
            "[Source 1]\nFile: goalkeeper_daniel_cohen.txt\nScore: 0.8\nContent: Salary 75000",
            [
                {"role": "user", "content": "Recommend a goalkeeper for build-up play."},
                {"role": "assistant", "content": "Daniel Cohen appears strongest."},
            ],
        )
        self.assertIn("Daniel Cohen", msg)
        self.assertIn("What salary does he expect?", msg)

    def test_unrelated_hebrew_question_refusal(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        result = engine.answer("מי זה דונלד טראמפ?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_HE)
        self.assertEqual(result["reason"], "out_of_domain")

    def test_legacy_diagnostic_template_has_placeholders(self):
        template = _build_bedrock_prompt_template("Test question")
        self.assertIn("$search_results$", template)
        self.assertIn("$query$", template)


class DomainAndDiversityTests(unittest.TestCase):
    """Out-of-domain guard, diverse retrieval, and comparison prompt checks."""

    def test_hebrew_trump_refused_exact_message(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        result = engine.answer("מי זה דונלד טראמפ?")
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_HE)
        self.assertEqual(result["reason"], "out_of_domain")
        engine._runtime_client.retrieve.assert_not_called()

    def test_english_trump_refused_exact_message(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        result = engine.answer("Who is Donald Trump?")
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_EN)
        self.assertEqual(result["reason"], "out_of_domain")

    def test_geography_question_refused(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        result = engine.answer("מהי בירת ניו זילנד?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_HE)
        self.assertEqual(result["reason"], "out_of_domain")

    def test_relevant_hebrew_question_allowed(self):
        self.assertTrue(_is_question_in_scoutmatch_domain("מי השוער המתאים ביותר?"))

    def test_full_hebrew_recruitment_question_allowed(self):
        self.assertTrue(
            _is_question_in_scoutmatch_domain(
                "אני מחפש שוער עם לפחות 5 שנות ניסיון, רגוע תחת לחץ, טוב במשחק רגל, "
                "מוכן לעבור לצפון ושכרו עד 80,000 אירו לעונה. מי המועמד המתאים ביותר ולמה?"
            )
        )

    def test_hebrew_goalkeeper_build_up_question_allowed(self):
        self.assertTrue(
            _is_question_in_scoutmatch_domain("מי השוער המתאים ביותר למשחק רגל?")
        )

    def test_hebrew_relocation_question_allowed(self):
        self.assertTrue(
            _is_question_in_scoutmatch_domain("איזה שחקן מוכן לעבור לצפון?")
        )

    def test_hebrew_salary_question_with_marco_silva_allowed(self):
        self.assertTrue(
            _is_question_in_scoutmatch_domain("כמה שכר דורש Marco Silva?")
        )

    def test_relevant_english_question_allowed(self):
        self.assertTrue(_is_question_in_scoutmatch_domain("Who is the best goalkeeper?"))

    def test_utf8_request_text_remains_valid(self):
        question = (
            "אני מחפש שוער עם לפחות 5 שנות ניסיון, רגוע תחת לחץ, טוב במשחק רגל, "
            "מוכן לעבור לצפון ושכרו עד 80,000 אירו לעונה. מי המועמד המתאים ביותר ולמה?"
        )
        encoded = json.dumps({"content": question}, ensure_ascii=False).encode("utf-8")
        decoded = encoded.decode("utf-8")
        self.assertIn("אני מחפש שוער", decoded)
        self.assertEqual(json.loads(decoded)["content"], question)
        self.assertTrue(_is_question_in_scoutmatch_domain(question))

    def test_follow_up_allowed_with_football_history(self):
        history = [
            {"role": "user", "content": "מי השוער המתאים ביותר למשחק רגל?"},
            {"role": "assistant", "content": "Daniel Cohen appears strongest."},
        ]
        self.assertTrue(_is_question_in_scoutmatch_domain("ומה השכר שלו?", history))

    def test_follow_up_refused_without_history(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        result = engine.answer("ומה השכר שלו?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "out_of_domain")

    def test_diverse_retrieval_includes_multiple_goalkeeper_files(self):
        uri_base = f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
        results = [
            {"text": f"chunk {i} same", "score": 0.9 - i * 0.01,
             "source": "goalkeeper_omer_azulay.txt", "s3_uri": f"{uri_base}player_cvs/goalkeeper_omer_azulay.txt"}
            for i in range(4)
        ] + [
            {"text": "Daniel build-up", "score": 0.85,
             "source": "goalkeeper_daniel_cohen.txt", "s3_uri": f"{uri_base}player_cvs/goalkeeper_daniel_cohen.txt"},
            {"text": "Yossi traditional", "score": 0.84,
             "source": "goalkeeper_yossi_levi.txt", "s3_uri": f"{uri_base}player_cvs/goalkeeper_yossi_levi.txt"},
            {"text": "Daniel report", "score": 0.83,
             "source": "goalkeeper_daniel_cohen_report.txt", "s3_uri": f"{uri_base}scouting_reports/goalkeeper_daniel_cohen_report.txt"},
        ]
        selected = _select_diverse_context_chunks(
            results,
            "מי המועמד המתאים ביותר?",
        )
        filenames = {_chunk_filename(c) for c in selected}
        self.assertIn("goalkeeper_daniel_cohen.txt", filenames)
        self.assertIn("goalkeeper_yossi_levi.txt", filenames)
        self.assertLessEqual(
            sum(1 for c in selected if _chunk_filename(c) == "goalkeeper_omer_azulay.txt"),
            config.AWS_KB_MAX_CHUNKS_PER_SOURCE,
        )

    def test_team_requirements_retained_for_comparison(self):
        uri_base = f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
        results = [
            {"text": "req", "score": 0.7,
             "source": "team_requirements.txt", "s3_uri": f"{uri_base}team_requirements/team_requirements.txt"},
            {"text": "daniel", "score": 0.9,
             "source": "goalkeeper_daniel_cohen.txt", "s3_uri": f"{uri_base}player_cvs/goalkeeper_daniel_cohen.txt"},
        ]
        selected = _select_diverse_context_chunks(results, "Who is the most suitable goalkeeper?")
        self.assertIn("team_requirements.txt", {_chunk_filename(c) for c in selected})

    def test_duplicate_filename_not_crowding_out(self):
        uri_base = f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
        results = [
            {"text": f"omer {i}", "score": 0.95 - i * 0.01,
             "source": "goalkeeper_omer_azulay.txt", "s3_uri": f"{uri_base}player_cvs/goalkeeper_omer_azulay.txt"}
            for i in range(5)
        ] + [{
            "text": "daniel", "score": 0.8,
            "source": "goalkeeper_daniel_cohen.txt", "s3_uri": f"{uri_base}player_cvs/goalkeeper_daniel_cohen.txt",
        }]
        selected = _select_diverse_context_chunks(results, "מי המועמד המתאים ביותר?")
        self.assertIn("goalkeeper_daniel_cohen.txt", {_chunk_filename(c) for c in selected})

    def test_stale_documents_never_reach_context(self):
        mixed = [
            {"text": "stale", "score": 0.99,
             "source": "knowledge_test.txt", "s3_uri": f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}knowledge_test.txt"},
            {"text": "course", "score": 0.98,
             "source": "docker_aws.pdf", "s3_uri": f"s3://{SCOUT_BUCKET}/data/docker_aws.pdf"},
            {"text": "valid", "score": 0.7,
             "source": "goalkeeper_daniel_cohen.txt", "s3_uri": SCOUT_GK_URI},
        ]
        selected = _select_diverse_context_chunks(mixed, "Who is the best goalkeeper?")
        filenames = {_chunk_filename(c) for c in selected}
        self.assertNotIn("knowledge_test.txt", filenames)
        self.assertNotIn("docker_aws.pdf", filenames)
        cards = chunks_to_source_cards(mixed)
        self.assertEqual(len(cards), 1)

    def test_prompt_numeric_and_budget_rules(self):
        prompt = EXPLICIT_GENERATION_PROMPT.lower()
        self.assertIn("4 years satisfies a minimum of 5 years", prompt)
        self.assertIn("90,000 eur satisfies a maximum budget of 80,000 eur", prompt)
        self.assertIn("relocation unwilling satisfies relocation required", prompt)

    def test_valid_grounded_recommendation_accepted(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _retrieve_payload(
            "Full Name: Daniel Cohen\nYears of Professional Experience: 6",
        )
        engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Daniel Cohen is the strongest match."
        )
        result = engine.answer("Who is the best goalkeeper for build-up play?")
        self.assertFalse(result["refused"])
        self.assertIn("Daniel Cohen", result["answer"])

    def test_marker_safety_still_blocks_passage_labels(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _retrieve_payload("Daniel Cohen CV")
        engine._bedrock_client.converse.return_value = _converse_response(
            "Daniel Cohen is noted in Passage %[4]%."
        )
        with patch("aws_kb_engine.sanitize_bedrock_answer", side_effect=lambda text: text):
            result = engine.answer("Who is the best goalkeeper?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "internal_markers")

    def test_english_unrelated_new_zealand_refused(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        result = engine.answer("What is the capital of New Zealand?")
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_EN)
        self.assertEqual(result["reason"], "out_of_domain")


def _chunk_filename(chunk: dict) -> str:
    return chunk.get("source", "")


class ReliabilityTests(unittest.TestCase):
    """Complete context selection and single name-retry behavior."""

    def test_short_hebrew_recommendation_accepted_with_explicit_name(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        uri_base = f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
        engine._runtime_client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "content": {"text": "COMPACT FACT PROFILE SUMMARY\nDaniel Cohen build-up strong"},
                    "score": 0.91,
                    "location": {"s3Location": {"uri": f"{uri_base}player_cvs/goalkeeper_daniel_cohen.txt"}},
                },
                {
                    "content": {"text": "Yossi Levi traditional shot-stopper"},
                    "score": 0.88,
                    "location": {"s3Location": {"uri": f"{uri_base}player_cvs/goalkeeper_yossi_levi.txt"}},
                },
            ]
        }
        engine._bedrock_client.converse.return_value = _converse_response(
            "על פי המסמכים שהועלו, Daniel Cohen הוא השוער המתאים ביותר למשחק רגל."
        )
        result = engine.answer("מי השוער המתאים ביותר למשחק רגל?")
        self.assertFalse(result["refused"])
        self.assertIn("Daniel Cohen", result["answer"])

    def test_name_retry_triggered_once_when_first_draft_lacks_name(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _retrieve_payload(
            "Full Name: Daniel Cohen\nProfessional Experience: 6 years",
        )
        engine._bedrock_client.converse.side_effect = [
            _converse_response("The most suitable candidate for build-up play is strong."),
            _converse_response("Based on the uploaded documents, Daniel Cohen is strongest."),
        ]
        result = engine.answer("Who is the best goalkeeper for build-up play?")
        self.assertFalse(result["refused"])
        self.assertIn("Daniel Cohen", result["answer"])
        self.assertEqual(engine._bedrock_client.converse.call_count, 2)

    def test_retry_adds_explicit_name_and_is_accepted(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _retrieve_payload(
            "Full Name: Daniel Cohen\nBuild-up ability strong",
        )
        engine._bedrock_client.converse.side_effect = [
            _converse_response("He is the strongest option for build-up play."),
            _converse_response("Daniel Cohen is the strongest option for build-up play."),
        ]
        result = engine.answer("Who is the best goalkeeper for build-up play?")
        self.assertFalse(result["refused"])
        self.assertIn("Daniel Cohen", result["answer"])

    def test_retry_still_without_name_returns_strict_refusal(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _retrieve_payload(
            "Full Name: Daniel Cohen\nProfessional Experience: 6 years",
        )
        engine._bedrock_client.converse.side_effect = [
            _converse_response("The strongest candidate fits build-up play."),
            _converse_response("The strongest candidate fits build-up play."),
        ]
        result = engine.answer("Who is the best goalkeeper for build-up play?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "no_explicit_name")
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_EN)

    def test_no_more_than_one_retry(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _retrieve_payload("Daniel Cohen CV")
        engine._bedrock_client.converse.side_effect = [
            _converse_response("The candidate is suitable."),
            _converse_response("Still no explicit player name here."),
        ]
        engine.answer("Who is the best goalkeeper for build-up play?")
        self.assertEqual(engine._bedrock_client.converse.call_count, 2)

    def test_two_useful_chunks_from_one_cv_may_enter_context(self):
        uri = SCOUT_GK_URI
        results = [
            {
                "text": "COMPACT FACT PROFILE SUMMARY\nDaniel Cohen | 6 years | 75,000 EUR",
                "score": 0.92,
                "source": "goalkeeper_daniel_cohen.txt",
                "s3_uri": uri,
            },
            {
                "text": "Professional profile: excellent back-pass distribution and composure.",
                "score": 0.86,
                "source": "goalkeeper_daniel_cohen.txt",
                "s3_uri": uri,
            },
        ]
        selected = _select_complete_diverse_context_chunks(
            results,
            "מי המועמד המתאים ביותר?",
        )
        daniel_chunks = [c for c in selected if _chunk_filename(c) == "goalkeeper_daniel_cohen.txt"]
        self.assertEqual(len(daniel_chunks), 2)

    def test_near_duplicate_chunks_deduplicated(self):
        first = {"text": "Daniel Cohen has six years experience", "score": 0.9}
        second = {"text": "Daniel Cohen has six years experience", "score": 0.85}
        self.assertTrue(_chunks_are_near_duplicate(first, second))

    def test_multiple_cv_files_preserve_diversity(self):
        uri_base = f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
        results = [
            {"text": "Daniel profile", "score": 0.9, "source": "goalkeeper_daniel_cohen.txt",
             "s3_uri": f"{uri_base}player_cvs/goalkeeper_daniel_cohen.txt"},
            {"text": "Yossi profile", "score": 0.88, "source": "goalkeeper_yossi_levi.txt",
             "s3_uri": f"{uri_base}player_cvs/goalkeeper_yossi_levi.txt"},
            {"text": "Omer profile", "score": 0.87, "source": "goalkeeper_omer_azulay.txt",
             "s3_uri": f"{uri_base}player_cvs/goalkeeper_omer_azulay.txt"},
        ]
        selected = _select_complete_diverse_context_chunks(results, "Who is the best goalkeeper?")
        self.assertEqual(len({_chunk_filename(c) for c in selected}), 3)

    def test_team_requirements_retained_in_complete_selection(self):
        uri_base = f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
        results = [
            {"text": "requirements", "score": 0.7, "source": "team_requirements.txt",
             "s3_uri": f"{uri_base}team_requirements/team_requirements.txt"},
            {"text": "daniel", "score": 0.9, "source": "goalkeeper_daniel_cohen.txt",
             "s3_uri": f"{uri_base}player_cvs/goalkeeper_daniel_cohen.txt"},
        ]
        selected = _select_complete_diverse_context_chunks(results, "Who is the best goalkeeper?")
        self.assertIn("team_requirements.txt", {_chunk_filename(c) for c in selected})

    def test_stale_files_never_enter_complete_context(self):
        mixed = [
            {"text": "stale", "score": 0.99, "source": "knowledge_test.txt",
             "s3_uri": f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}knowledge_test.txt"},
            {"text": "course", "score": 0.98, "source": "docker_aws.pdf",
             "s3_uri": f"s3://{SCOUT_BUCKET}/data/docker_aws.pdf"},
            {"text": "valid", "score": 0.7, "source": "goalkeeper_daniel_cohen.txt", "s3_uri": SCOUT_GK_URI},
        ]
        selected = _select_complete_diverse_context_chunks(mixed, "Who is the best goalkeeper?")
        filenames = {_chunk_filename(c) for c in selected}
        self.assertNotIn("knowledge_test.txt", filenames)
        self.assertNotIn("docker_aws.pdf", filenames)

    def test_daniel_cohen_context_includes_experience_and_salary(self):
        uri = SCOUT_GK_URI
        results = [
            {
                "text": "COMPACT FACT PROFILE SUMMARY\nProfessional Experience: 6 years\nAnnual Salary Expectation: 75,000 EUR",
                "score": 0.95,
                "source": "goalkeeper_daniel_cohen.txt",
                "s3_uri": uri,
            },
            {
                "text": "Daniel Cohen excels in build-up distribution.",
                "score": 0.84,
                "source": "goalkeeper_daniel_cohen.txt",
                "s3_uri": uri,
            },
        ]
        selected = _select_complete_diverse_context_chunks(results, "מי המועמד המתאים ביותר?")
        combined = " ".join(c.get("text", "") for c in selected).lower()
        self.assertIn("6 years", combined)
        self.assertIn("75,000", combined)

    def test_numeric_consistency_still_rejects_four_vs_five(self):
        accepted, reason = validate_final_answer(
            "Which goalkeeper has at least 5 years of experience?",
            "The candidate has 4 years, which meets the requirement of at least 5 years.",
            [{"source": "goalkeeper_daniel_cohen.txt", "text": "Daniel Cohen"}],
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "numeric_contradiction")

    def test_budget_consistency_still_rejects_ninety_vs_eighty(self):
        accepted, reason = validate_final_answer(
            "Who fits an 80,000 EUR maximum budget?",
            "90,000 EUR meets the maximum budget of 80,000 EUR.",
            [{"source": "goalkeeper_omer_azulay.txt", "text": "Omer Azulay"}],
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "numeric_contradiction")

    def test_follow_up_salary_after_named_recommendation(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        uri_base = f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
        engine._runtime_client.retrieve.return_value = {
            "retrievalResults": [{
                "content": {"text": "Daniel Cohen salary 75,000 EUR"},
                "score": 0.9,
                "location": {"s3Location": {"uri": f"{uri_base}player_cvs/goalkeeper_daniel_cohen.txt"}},
            }]
        }
        engine._bedrock_client.converse.return_value = _converse_response(
            "Daniel Cohen expects 75,000 EUR per year."
        )
        history = [
            {"role": "user", "content": "מי השוער המתאים ביותר למשחק רגל?"},
            {"role": "assistant", "content": "Daniel Cohen is the strongest build-up goalkeeper."},
        ]
        result = engine.answer("ומה השכר שלו?", history=history)
        self.assertFalse(result["refused"])
        self.assertIn("75,000", result["answer"])

    def test_out_of_domain_trump_still_exact_refusal(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        result = engine.answer("מי זה דונלד טראמפ?")
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_HE)
        self.assertEqual(result["reason"], "out_of_domain")
        self.assertEqual(result["context"], [])

    def test_name_retry_instruction_present(self):
        self.assertIn("did not name a player explicitly", _NAME_RETRY_INSTRUCTION.lower())
        self.assertIn("english name", _NAME_RETRY_INSTRUCTION.lower())

    def test_hebrew_player_name_accepted_in_validation(self):
        accepted, reason = validate_final_answer(
            "מי השוער המתאים ביותר למשחק רגל?",
            "על פי המסמכים, דניאל כהן הוא המועמד המתאים ביותר למשחק רגל.",
            [{"source": "goalkeeper_daniel_cohen.txt", "text": "Full Name: Daniel Cohen"}],
        )
        self.assertTrue(accepted)
        self.assertIsNone(reason)

    def test_timestamped_duplicate_sources_collapse_to_canonical(self):
        uri_base = f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
        results = [
            {"text": "profile summary", "score": 0.95,
             "source": "goalkeeper_daniel_cohen_20260531_173605.txt",
             "s3_uri": f"{uri_base}player_cvs/goalkeeper_daniel_cohen_20260531_173605.txt"},
            {"text": "COMPACT FACT PROFILE SUMMARY\n6 years", "score": 0.9,
             "source": "goalkeeper_daniel_cohen.txt",
             "s3_uri": f"{uri_base}player_cvs/goalkeeper_daniel_cohen.txt"},
        ]
        selected = _select_complete_diverse_context_chunks(results, "מי המועמד המתאים ביותר?")
        canonical = {_canonical_source_key(_chunk_filename(c)) for c in selected}
        self.assertEqual(len(canonical), 1)
        self.assertIn("goalkeeper_daniel_cohen", canonical)


class AWSStorageTests(unittest.TestCase):
    def setUp(self):
        self.svc = AWSStorageService()
        self.svc._s3 = MagicMock()
        self.svc._bedrock_agent = MagicMock()

    def test_validate_safe_filename(self):
        safe, ext = self.svc.validate_upload("daniel_cohen_cv.txt", 1024)
        self.assertEqual(safe, "daniel_cohen_cv.txt")
        self.assertEqual(ext, ".txt")

    def test_validate_pdf_docx_csv_extensions(self):
        for filename, expected_ext in (
            ("player_profile.pdf", ".pdf"),
            ("scouting_report.docx", ".docx"),
            ("squad_stats.csv", ".csv"),
        ):
            with self.subTest(filename=filename):
                safe, ext = self.svc.validate_upload(filename, 512)
                self.assertEqual(ext, expected_ext)
                self.assertTrue(safe.endswith(expected_ext))

    def test_reject_unsupported_extension(self):
        with self.assertRaises(UploadValidationError) as ctx:
            self.svc.validate_upload("malware.exe", 100)
        self.assertIn("Unsupported file type", str(ctx.exception))
        self.assertIn(".exe", str(ctx.exception))

    def test_reject_path_traversal(self):
        with self.assertRaises(UploadValidationError):
            self.svc.validate_upload("../secret.txt", 100)

    def test_upload_to_scoutmatch_prefix(self):
        self.svc._s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadObject",
        )
        self.svc._s3.put_object.return_value = {}
        result = self.svc.upload_bytes(b"CV content", "goalkeeper_daniel_cohen.txt")
        self.assertIn("scoutmatch/knowledge-base/", result["key"])
        self.assertIn("player_cvs", result["key"])
        self.svc._s3.put_object.assert_called_once()

    def test_session_upload_uses_session_prefix_and_sidecar_metadata(self):
        self.svc._s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadObject",
        )
        self.svc._s3.put_object.return_value = {}
        result = self.svc.upload_session_document(
            b"CV content",
            "goalkeeper_daniel_cohen.txt",
            session_id=TEST_SESSION_ID,
            category="PLAYER CV",
        )
        expected_prefix = f"{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/"
        self.assertTrue(result["key"].startswith(expected_prefix))
        self.assertEqual(result["metadata_key"], result["key"] + ".metadata.json")
        metadata_call = self.svc._s3.put_object.call_args_list[1]
        metadata = json.loads(metadata_call.kwargs["Body"].decode("utf-8"))
        self.assertEqual(metadata["metadataAttributes"]["session_id"], TEST_SESSION_ID)
        self.assertEqual(metadata["metadataAttributes"]["category"], "PLAYER CV")

    def _session_upload(self, filename: str, content: bytes) -> dict:
        self.svc._s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadObject",
        )
        self.svc._s3.put_object.return_value = {}
        return self.svc.upload_session_document(
            content,
            filename,
            session_id=TEST_SESSION_ID,
            category="PLAYER CV",
        )

    def test_session_upload_pdf_docx_csv_use_session_prefix_and_sidecar(self):
        samples = {
            "forward_audit_player.pdf": b"%PDF-1.4 audit player profile",
            "forward_audit_player.docx": b"PK audit docx content",
            "forward_audit_player.csv": b"Name,Position\nAudit Player,ST\n",
        }
        expected_prefix = f"{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/"
        for filename, content in samples.items():
            with self.subTest(filename=filename):
                result = self._session_upload(filename, content)
                self.assertTrue(result["key"].startswith(expected_prefix))
                self.assertEqual(result["metadata_key"], result["key"] + ".metadata.json")
                metadata_call = self.svc._s3.put_object.call_args_list[-1]
                metadata = json.loads(metadata_call.kwargs["Body"].decode("utf-8"))
                self.assertEqual(metadata["metadataAttributes"]["session_id"], TEST_SESSION_ID)
                self.svc._s3.put_object.reset_mock()

    def test_list_session_documents_only_active_prefix(self):
        paginator = MagicMock()
        paginator.paginate.return_value = [{
            "Contents": [
                {"Key": f"{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/gk.txt", "Size": 100, "LastModified": None},
                {"Key": f"{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/gk.txt.metadata.json", "Size": 10, "LastModified": None},
            ]
        }]
        self.svc._s3.get_paginator.return_value = paginator
        docs = self.svc.list_session_documents(TEST_SESSION_ID)
        self.assertEqual(len(docs), 1)
        self.assertIn(f"sessions/{TEST_SESSION_ID}/", docs[0]["key"])

    def test_delete_recorded_session_objects_deletes_source_and_sidecar(self):
        result = self.svc.delete_recorded_session_objects([
            {"s3_key": f"{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/gk.txt"}
        ])
        self.assertEqual(result["deleted"], 2)
        objects = self.svc._s3.delete_objects.call_args.kwargs["Delete"]["Objects"]
        keys = {obj["Key"] for obj in objects}
        self.assertIn(f"{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/gk.txt", keys)
        self.assertIn(f"{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/gk.txt.metadata.json", keys)

    def test_start_ingestion_job(self):
        self.svc._bedrock_agent.start_ingestion_job.return_value = {
            "ingestionJob": {"ingestionJobId": "JOB123", "status": "STARTING"}
        }
        job = self.svc.start_ingestion_job()
        self.assertEqual(job["ingestion_job_id"], "JOB123")
        self.assertEqual(job["status"], "STARTING")

    def test_ingestion_status_complete(self):
        self.svc._latest_ingestion_job = {"ingestion_job_id": "JOB123", "status": "STARTING"}
        self.svc._bedrock_agent.get_ingestion_job.return_value = {
            "ingestionJob": {"status": "COMPLETE", "statistics": {}}
        }
        status = self.svc.get_ingestion_status("JOB123")
        self.assertEqual(status["status"], "COMPLETE")

    def test_list_only_scoutmatch_prefix(self):
        paginator = MagicMock()
        paginator.paginate.return_value = [{
            "Contents": [
                {"Key": "scoutmatch/knowledge-base/player_cvs/gk.txt", "Size": 100, "LastModified": None},
                {"Key": "scoutmatch/knowledge-base/scouting_reports/gk_report.txt", "Size": 80, "LastModified": None},
            ]
        }]
        self.svc._s3.get_paginator.return_value = paginator
        docs = self.svc.list_documents()
        self.assertEqual(len(docs), 2)
        self.assertTrue(all("scoutmatch/knowledge-base/" in d["key"] for d in docs))


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self._orig = database.DB_PATH
        database.DB_PATH = self.tmp.name
        database._local.conn = None
        database.init_db()

    def tearDown(self):
        conn = getattr(database._local, "conn", None)
        if conn is not None:
            conn.close()
            database._local.conn = None
        database.DB_PATH = self._orig
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_new_conversation_no_s3_side_effects(self):
        s1 = database.create_session()
        s2 = database.create_session()
        self.assertNotEqual(s1["id"], s2["id"])
        self.assertEqual(database.list_session_documents(s1["id"]), [])
        self.assertEqual(database.list_session_documents(s2["id"]), [])

    def test_session_documents_are_isolated(self):
        s1 = database.create_session()
        s2 = database.create_session()
        doc = database.add_session_document(
            s1["id"],
            f"{SCOUT_PREFIX}sessions/{s1['id']}/gk.txt",
            "gk.txt",
            "PLAYER CV",
        )
        self.assertEqual(len(database.list_session_documents(s1["id"])), 1)
        self.assertEqual(database.list_session_documents(s2["id"]), [])
        self.assertEqual(database.get_session_document(s1["id"], doc["id"])["display_name"], "gk.txt")
        deleted = database.delete_session_document(s1["id"], doc["id"])
        self.assertEqual(deleted["s3_key"], f"{SCOUT_PREFIX}sessions/{s1['id']}/gk.txt")
        self.assertEqual(database.list_session_documents(s1["id"]), [])

    def test_clear_session_documents_returns_only_active_docs(self):
        s1 = database.create_session()
        s2 = database.create_session()
        database.add_session_document(s1["id"], f"{SCOUT_PREFIX}sessions/{s1['id']}/a.txt", "a.txt", "TXT")
        database.add_session_document(s2["id"], f"{SCOUT_PREFIX}sessions/{s2['id']}/b.txt", "b.txt", "TXT")
        cleared = database.clear_session_documents(s1["id"])
        self.assertEqual(len(cleared), 1)
        self.assertEqual(database.list_session_documents(s1["id"]), [])
        self.assertEqual(len(database.list_session_documents(s2["id"])), 1)

    def test_find_session_documents_by_display_name(self):
        session = database.create_session()
        database.add_session_document(
            session["id"],
            f"{SCOUT_PREFIX}sessions/{session['id']}/ScoutMatch-Admin-Token.txt",
            "ScoutMatch-Admin-Token.txt",
            "TXT",
        )
        matches = database.find_session_documents_by_display_name("ScoutMatch-Admin-Token.txt")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["session_id"], session["id"])

    def test_database_path_parent_created_for_persistent_mount(self):
        conn = getattr(database._local, "conn", None)
        if conn is not None:
            conn.close()
            database._local.conn = None
        nested_dir = Path(self.tmp.name).with_suffix("") / "runtime"
        nested_db = nested_dir / "chat.db"
        database.DB_PATH = str(nested_db)
        database.init_db()
        self.assertTrue(nested_db.exists())
        conn = getattr(database._local, "conn", None)
        if conn is not None:
            conn.close()
            database._local.conn = None

    def test_delete_conversation_only_local(self):
        s = database.create_session()
        database.add_message(s["id"], "user", "Hello")
        database.delete_session(s["id"])
        self.assertIsNone(database.get_session(s["id"]))

    def test_bedrock_session_id_storage(self):
        s = database.create_session()
        database.update_bedrock_session_id(s["id"], "br-session-abc")
        updated = database.get_session(s["id"])
        self.assertEqual(updated["bedrock_session_id"], "br-session-abc")


class FollowUpTests(unittest.TestCase):
    def test_history_included_in_prompt(self):
        from aws_kb_engine import _build_conversation_history_text

        text = _build_conversation_history_text(
            [
                {"role": "user", "content": "Recommend a goalkeeper for build-up play."},
                {"role": "assistant", "content": "Daniel Cohen appears to be the strongest match."},
            ],
        )
        self.assertIn("Daniel Cohen", text)


class SessionScopedRetrievalTests(unittest.TestCase):
    def test_retrieve_sends_metadata_filter_equals_session_id(self):
        engine = AWSKnowledgeBaseEngine()
        engine.ready = True
        engine._runtime_client = MagicMock()
        engine._runtime_client.retrieve.return_value = _retrieve_payload(
            DANIEL_PROFILE,
            uri=SCOUT_GK_URI,
        )
        results = engine.retrieve("Which goalkeeper fits?", session_id=TEST_SESSION_ID)
        self.assertEqual(len(results), 1)
        config_arg = engine._runtime_client.retrieve.call_args.kwargs["retrievalConfiguration"]
        self.assertEqual(
            config_arg["vectorSearchConfiguration"]["filter"],
            {"equals": {"key": "session_id", "value": TEST_SESSION_ID}},
        )

    def test_uri_guard_rejects_another_session(self):
        other_uri = (
            f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}sessions/other-session/gk.txt"
        )
        self.assertFalse(_is_allowed_session_source(other_uri, TEST_SESSION_ID))

    def test_answer_without_session_id_refuses_safely(self):
        engine = AWSKnowledgeBaseEngine()
        engine.ready = True
        engine._runtime_client = MagicMock()
        engine._bedrock_client = MagicMock()
        result = engine.answer("Which goalkeeper fits build-up play?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "missing_session_id")
        engine._runtime_client.retrieve.assert_not_called()


class SessionDocumentApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.tmp_data = tempfile.TemporaryDirectory()
        self._orig_db = database.DB_PATH
        self._orig_token = config.SCOUTMATCH_ADMIN_TOKEN
        self._orig_rag_backend = config.RAG_BACKEND
        self._orig_data_dir = config.DATA_DIR
        database.DB_PATH = self.tmp.name
        database._local.conn = None
        database.init_db()
        config.SCOUTMATCH_ADMIN_TOKEN = "test-admin-token"

        import app as flask_app

        self.flask_app = flask_app
        self.client = flask_app.app.test_client()
        flask_app.app.config["TESTING"] = True

        self.svc = AWSStorageService()
        self.svc._s3 = MagicMock()
        self.svc._bedrock_agent = MagicMock()
        self.svc._s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadObject",
        )
        self.svc._bedrock_agent.start_ingestion_job.return_value = {
            "ingestionJob": {"ingestionJobId": "JOB123", "status": "STARTING"}
        }
        self.storage_patch = patch.object(flask_app, "aws_storage", self.svc)
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        conn = getattr(database._local, "conn", None)
        if conn is not None:
            conn.close()
            database._local.conn = None
        database.DB_PATH = self._orig_db
        config.SCOUTMATCH_ADMIN_TOKEN = self._orig_token
        config.RAG_BACKEND = self._orig_rag_backend
        config.DATA_DIR = self._orig_data_dir
        Path(self.tmp.name).unlink(missing_ok=True)
        self.tmp_data.cleanup()

    def _create_session(self) -> dict:
        resp = self.client.post("/api/sessions", json={})
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()

    def test_upload_requires_and_uses_session_id_and_records_row(self):
        session = self._create_session()
        resp = self.client.post(
            f"/api/sessions/{session['id']}/documents/upload",
            data={"file": (io.BytesIO(b"CV content"), "goalkeeper_daniel_cohen.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.get_json()
        self.assertIn(f"sessions/{session['id']}/", body["key"])
        docs = database.list_session_documents(session["id"])
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["s3_key"], body["key"])

    def _upload_file(self, session_id: str, filename: str, content: bytes):
        return self.client.post(
            f"/api/sessions/{session_id}/documents/upload",
            data={"file": (io.BytesIO(content), filename)},
            content_type="multipart/form-data",
        )

    def test_upload_txt_pdf_docx_csv_session_scoped_with_ingestion(self):
        session = self._create_session()
        uploads = {
            "goalkeeper_audit.txt": b"Full Name: Audit Goalkeeper\nPosition: GK\n",
            "goalkeeper_audit.pdf": b"%PDF-1.4 audit goalkeeper profile",
            "goalkeeper_audit.docx": b"PK audit goalkeeper docx",
            "goalkeeper_audit.csv": b"Name,Position\nAudit Goalkeeper,GK\n",
        }
        for filename, content in uploads.items():
            with self.subTest(filename=filename):
                resp = self._upload_file(session["id"], filename, content)
                self.assertEqual(resp.status_code, 201, resp.get_json())
                body = resp.get_json()
                self.assertIn(f"sessions/{session['id']}/", body["key"])
                self.assertEqual(body.get("ingestion_job_id"), "JOB123")
        self.svc._bedrock_agent.start_ingestion_job.assert_called()
        self.assertEqual(len(database.list_session_documents(session["id"])), len(uploads))

    def test_upload_unsupported_extension_rejected(self):
        session = self._create_session()
        resp = self._upload_file(session["id"], "bad_file.exe", b"binary")
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertIn("Unsupported file type", body.get("error", ""))
        self.assertEqual(database.list_session_documents(session["id"]), [])
        self.svc._bedrock_agent.start_ingestion_job.assert_not_called()

    def test_listing_returns_only_active_session_documents(self):
        s1 = self._create_session()
        s2 = self._create_session()
        database.add_session_document(s1["id"], f"{SCOUT_PREFIX}sessions/{s1['id']}/a.txt", "a.txt", "TXT")
        database.add_session_document(s2["id"], f"{SCOUT_PREFIX}sessions/{s2['id']}/b.txt", "b.txt", "TXT")
        resp = self.client.get(f"/api/sessions/{s1['id']}/documents")
        self.assertEqual(resp.status_code, 200)
        docs = resp.get_json()["documents"]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["display_name"], "a.txt")

    def test_clear_documents_works_without_admin_token_and_deletes_sidecars(self):
        session = self._create_session()
        database.add_session_document(
            session["id"],
            f"{SCOUT_PREFIX}sessions/{session['id']}/a.txt",
            "a.txt",
            "TXT",
        )
        ok = self.client.post(f"/api/sessions/{session['id']}/documents/clear")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(database.list_session_documents(session["id"]), [])
        objects = self.svc._s3.delete_objects.call_args.kwargs["Delete"]["Objects"]
        keys = {obj["Key"] for obj in objects}
        self.assertIn(f"{SCOUT_PREFIX}sessions/{session['id']}/a.txt", keys)
        self.assertIn(f"{SCOUT_PREFIX}sessions/{session['id']}/a.txt.metadata.json", keys)
        self.svc._bedrock_agent.start_ingestion_job.assert_called_once()

    def test_clear_documents_without_objects_skips_ingestion_sync(self):
        session = self._create_session()
        resp = self.client.post(f"/api/sessions/{session['id']}/documents/clear")
        self.assertEqual(resp.status_code, 200)
        self.svc._s3.delete_objects.assert_not_called()
        self.svc._bedrock_agent.start_ingestion_job.assert_not_called()

    def test_clear_documents_does_not_delete_other_session_or_legacy_objects(self):
        s1 = self._create_session()
        s2 = self._create_session()
        database.add_session_document(
            s1["id"],
            f"{SCOUT_PREFIX}sessions/{s1['id']}/a.txt",
            "a.txt",
            "TXT",
        )
        database.add_session_document(
            s2["id"],
            f"{SCOUT_PREFIX}sessions/{s2['id']}/b.txt",
            "b.txt",
            "TXT",
        )
        resp = self.client.post(f"/api/sessions/{s1['id']}/documents/clear")
        self.assertEqual(resp.status_code, 200)
        objects = self.svc._s3.delete_objects.call_args.kwargs["Delete"]["Objects"]
        keys = {obj["Key"] for obj in objects}
        self.assertTrue(all(f"sessions/{s1['id']}/" in key for key in keys))
        self.assertFalse(any(f"sessions/{s2['id']}/" in key for key in keys))
        self.assertFalse(any("player_cvs/" in key for key in keys))
        self.assertEqual(len(database.list_session_documents(s1["id"])), 0)
        self.assertEqual(len(database.list_session_documents(s2["id"])), 1)

    def test_clear_documents_refuses_non_session_prefix_and_preserves_db(self):
        session = self._create_session()
        database.add_session_document(
            session["id"],
            f"{SCOUT_PREFIX}player_cvs/legacy_global.txt",
            "legacy_global.txt",
            "TXT",
        )
        resp = self.client.post(f"/api/sessions/{session['id']}/documents/clear")
        self.assertEqual(resp.status_code, 503)
        self.svc._s3.delete_objects.assert_not_called()
        self.assertEqual(len(database.list_session_documents(session["id"])), 1)

    def test_delete_single_document_without_admin_token(self):
        session = self._create_session()
        doc = database.add_session_document(
            session["id"],
            f"{SCOUT_PREFIX}sessions/{session['id']}/a.txt",
            "a.txt",
            "TXT",
        )
        resp = self.client.delete(
            f"/api/sessions/{session['id']}/documents/{doc['id']}",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(database.list_session_documents(session["id"]), [])
        objects = self.svc._s3.delete_objects.call_args.kwargs["Delete"]["Objects"]
        keys = {obj["Key"] for obj in objects}
        self.assertIn(f"{SCOUT_PREFIX}sessions/{session['id']}/a.txt", keys)
        self.assertIn(f"{SCOUT_PREFIX}sessions/{session['id']}/a.txt.metadata.json", keys)
        self.svc._bedrock_agent.start_ingestion_job.assert_called_once()

    def test_delete_conversation_history_only_keeps_s3_documents(self):
        session = self._create_session()
        database.add_session_document(
            session["id"],
            f"{SCOUT_PREFIX}sessions/{session['id']}/a.txt",
            "a.txt",
            "TXT",
        )
        resp = self.client.delete(f"/api/sessions/{session['id']}", json={"delete_documents": False})
        self.assertEqual(resp.status_code, 200)
        self.svc._s3.delete_objects.assert_not_called()
        self.svc._bedrock_agent.start_ingestion_job.assert_not_called()
        self.assertIsNone(database.get_session(session["id"]))

    def test_delete_conversation_with_documents_without_admin_token(self):
        session = self._create_session()
        database.add_message(session["id"], "user", "hello")
        database.add_session_document(
            session["id"],
            f"{SCOUT_PREFIX}sessions/{session['id']}/a.txt",
            "a.txt",
            "TXT",
        )
        ok = self.client.delete(
            f"/api/sessions/{session['id']}",
            json={"delete_documents": True},
        )
        self.assertEqual(ok.status_code, 200)
        self.svc._s3.delete_objects.assert_called_once()
        self.svc._bedrock_agent.start_ingestion_job.assert_called_once()
        self.assertIsNone(database.get_session(session["id"]))

    def test_delete_conversation_without_documents_skips_ingestion_sync(self):
        session = self._create_session()
        resp = self.client.delete(
            f"/api/sessions/{session['id']}",
            json={"delete_documents": True},
        )
        self.assertEqual(resp.status_code, 200)
        self.svc._s3.delete_objects.assert_not_called()
        self.svc._bedrock_agent.start_ingestion_job.assert_not_called()

    def test_delete_conversation_does_not_affect_other_session(self):
        s1 = self._create_session()
        s2 = self._create_session()
        database.add_session_document(
            s1["id"],
            f"{SCOUT_PREFIX}sessions/{s1['id']}/a.txt",
            "a.txt",
            "TXT",
        )
        database.add_session_document(
            s2["id"],
            f"{SCOUT_PREFIX}sessions/{s2['id']}/b.txt",
            "b.txt",
            "TXT",
        )
        resp = self.client.delete(f"/api/sessions/{s1['id']}", json={"delete_documents": True})
        self.assertEqual(resp.status_code, 200)
        objects = self.svc._s3.delete_objects.call_args.kwargs["Delete"]["Objects"]
        keys = {obj["Key"] for obj in objects}
        self.assertTrue(all(f"sessions/{s1['id']}/" in key for key in keys))
        self.assertFalse(any(f"sessions/{s2['id']}/" in key for key in keys))
        self.assertIsNone(database.get_session(s1["id"]))
        self.assertIsNotNone(database.get_session(s2["id"]))
        self.assertEqual(len(database.list_session_documents(s2["id"])), 1)

    def test_delete_conversation_refuses_legacy_global_key_and_preserves_session(self):
        session = self._create_session()
        database.add_session_document(
            session["id"],
            f"{SCOUT_PREFIX}player_cvs/legacy_global.txt",
            "legacy_global.txt",
            "TXT",
        )
        resp = self.client.delete(f"/api/sessions/{session['id']}", json={"delete_documents": True})
        self.assertEqual(resp.status_code, 503)
        self.svc._s3.delete_objects.assert_not_called()
        self.assertIsNotNone(database.get_session(session["id"]))

    def test_delete_conversation_leaves_remaining_session_selectable(self):
        s1 = self._create_session()
        s2 = self._create_session()
        resp = self.client.delete(f"/api/sessions/{s1['id']}", json={"delete_documents": True})
        self.assertEqual(resp.status_code, 200)
        remaining = self.client.get("/api/sessions").get_json()["sessions"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], s2["id"])
        detail = self.client.get(f"/api/sessions/{s2['id']}")
        self.assertEqual(detail.status_code, 200)

    def test_local_mode_session_upload_list_and_clear(self):
        config.RAG_BACKEND = "local"
        config.DATA_DIR = Path(self.tmp_data.name)
        session = self._create_session()
        with patch.object(self.flask_app, "_reindex_engine_background", return_value=None):
            upload = self.client.post(
                f"/api/sessions/{session['id']}/documents/upload",
                data={"file": (io.BytesIO(b"Local CV"), "local_goalkeeper.txt")},
                content_type="multipart/form-data",
            )
        self.assertEqual(upload.status_code, 201)
        key = upload.get_json()["key"]
        self.assertIn(f"session_uploads/{session['id']}/", key)
        listed = self.client.get(f"/api/sessions/{session['id']}/documents")
        self.assertEqual(len(listed.get_json()["documents"]), 1)
        with patch.object(self.flask_app, "_reindex_engine_background", return_value=None):
            cleared = self.client.post(f"/api/sessions/{session['id']}/documents/clear")
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(database.list_session_documents(session["id"]), [])


class UISmokeTests(unittest.TestCase):
    def test_homepage_renders_scoutmatch(self):
        import app as flask_app

        flask_app.app.config["TESTING"] = True
        client = flask_app.app.test_client()
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ScoutMatch AI", html)
        self.assertIn("Upload CV", html)
        self.assertIn("Clear documents", html)
        self.assertIn("Grounded answers only", html)

    def test_frontend_uses_session_scoped_document_endpoints(self):
        js = (PROJECT_ROOT / "static/js/app.js").read_text(encoding="utf-8")
        html = (PROJECT_ROOT / "templates/index.html").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "static/css/style.css").read_text(encoding="utf-8")
        self.assertIn("/api/sessions/${sessionId}/documents", js)
        self.assertIn("clearSessionDocuments", js)
        self.assertIn("deleteSessionDocument", js)
        self.assertIn("document-list__delete", js)
        self.assertIn("homeHero", js)
        self.assertIn("messages--landing", js)
        self.assertIn("messages--has-chat", js)
        self.assertNotIn("X-ScoutMatch-Admin-Token", js)
        self.assertNotIn("Admin token required", js)
        self.assertIn("home-dashboard-art.png", html)
        self.assertIn("hero-right", html)
        self.assertIn("dashboard-stage__panel-img", html)
        self.assertIn("messages--landing", css)
        self.assertIn("home-dashboard-art.png", css)
        self.assertIn("messages--has-chat::before", css)
        self.assertIn("messages--has-chat::after", css)
        self.assertIn("messages__inner", css)
        self.assertRegex(
            css,
            r"messages--has-chat::before[\s\S]*home-dashboard-art\.png",
        )
        self.assertRegex(
            css,
            r"messages--has-chat::after[\s\S]*linear-gradient\(\s*to right",
        )
        self.assertRegex(css, r"messages--has-chat \.messages__inner[\s\S]*z-index:\s*1")

    def test_upload_input_accepts_required_formats(self):
        html = (PROJECT_ROOT / "templates/index.html").read_text(encoding="utf-8")
        for ext in (".txt", ".pdf", ".docx", ".csv"):
            self.assertIn(ext, html, f"missing accept extension {ext}")

    def test_health_and_status(self):
        import app as flask_app

        flask_app.app.config["TESTING"] = True
        client = flask_app.app.test_client()
        health = client.get("/api/health").get_json()
        self.assertTrue(health.get("ok"))
        status = client.get("/api/status").get_json()
        self.assertIn("rag_backend", status)
        self.assertEqual(status.get("app_name"), "ScoutMatch AI")


class SourceExtractionTests(unittest.TestCase):
    def test_extract_sources_from_citations(self):
        sources = extract_sources_from_citations([{
            "retrievedReferences": [{
                "content": {"text": "Salary expectation: 75000 EUR"},
                "location": {"s3Location": {"uri": SCOUT_GK_URI}},
            }]
        }])
        self.assertEqual(len(sources), 1)
        self.assertIn("daniel", sources[0]["source"].lower())


class VerifiedMatrixTests(unittest.TestCase):
    """Deterministic requirement verification and matrix validation."""

    def test_parse_daniel_cohen_facts(self):
        facts = extract_verified_player_facts([
            _player_chunk("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE),
        ])[0]
        self.assertEqual(facts["full_name"], "Daniel Cohen")
        self.assertEqual(facts["professional_experience_years"], 6)
        self.assertEqual(facts["annual_salary_eur"], 75000)
        self.assertEqual(facts["relocation_north"], "YES")

    def test_parse_yossi_levi_facts(self):
        facts = extract_verified_player_facts([
            _player_chunk("goalkeeper_yossi_levi.txt", YOSSI_PROFILE),
        ])[0]
        self.assertEqual(facts["professional_experience_years"], 9)
        self.assertEqual(facts["annual_salary_eur"], 65000)
        self.assertEqual(facts["relocation_north"], "NO")

    def test_parse_omer_azulay_facts(self):
        facts = extract_verified_player_facts([
            _player_chunk("goalkeeper_omer_azulay.txt", OMER_PROFILE),
        ])[0]
        self.assertEqual(facts["professional_experience_years"], 8)
        self.assertEqual(facts["annual_salary_eur"], 90000)
        self.assertEqual(facts["relocation_north"], "MAYBE")

    def test_parse_hebrew_requirements(self):
        question = (
            "אני מחפש שוער עם לפחות 5 שנות ניסיון, רגוע תחת לחץ, "
            "טוב במשחק רגל, מוכן לעבור לצפון ושכרו עד 80,000 אירו"
        )
        reqs = extract_recruitment_requirements(question)
        self.assertEqual(reqs["min_experience_years"], 5)
        self.assertEqual(reqs["max_salary_eur"], 80000)
        self.assertTrue(reqs["relocation_north_required"])
        self.assertTrue(reqs["calm_under_pressure_required"])
        self.assertTrue(reqs["build_up_required"])

    def test_parse_english_requirements(self):
        question = (
            "Goalkeeper with at least 5 years, calm under pressure, "
            "good with his feet, willing to relocate north, up to 80,000 EUR"
        )
        reqs = extract_recruitment_requirements(question)
        self.assertEqual(reqs["min_experience_years"], 5)
        self.assertEqual(reqs["max_salary_eur"], 80000)
        self.assertTrue(reqs["relocation_north_required"])
        self.assertTrue(reqs["calm_under_pressure_required"])
        self.assertTrue(reqs["build_up_required"])

    def test_daniel_six_vs_minimum_five_passes(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE),
            ]),
            {"min_experience_years": 5, "max_salary_eur": None,
             "relocation_north_required": False, "build_up_required": False,
             "calm_under_pressure_required": False, "position": "goalkeeper"},
        )
        self.assertEqual(matrix["candidates"][0]["checks"]["experience"], "PASS")

    def test_four_vs_minimum_five_fails(self):
        matrix = build_verified_candidate_matrix(
            [{"full_name": "Test Player", "professional_experience_years": 4,
              "source_filenames": ["goalkeeper_test.txt"]}],
            {"min_experience_years": 5, "max_salary_eur": None,
             "relocation_north_required": False, "build_up_required": False,
             "calm_under_pressure_required": False, "position": None},
        )
        self.assertEqual(matrix["candidates"][0]["checks"]["experience"], "FAIL")

    def test_omer_ninety_vs_eighty_fails(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_omer_azulay.txt", OMER_PROFILE),
            ]),
            {"min_experience_years": None, "max_salary_eur": 80000,
             "relocation_north_required": False, "build_up_required": False,
             "calm_under_pressure_required": False, "position": None},
        )
        self.assertEqual(matrix["candidates"][0]["checks"]["salary"], "FAIL")

    def test_yossi_relocation_no_fails_when_required(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_yossi_levi.txt", YOSSI_PROFILE),
            ]),
            {"min_experience_years": None, "max_salary_eur": None,
             "relocation_north_required": True, "build_up_required": False,
             "calm_under_pressure_required": False, "position": None},
        )
        self.assertEqual(matrix["candidates"][0]["checks"]["relocation_north"], "FAIL")

    def test_unknown_value_never_passes(self):
        matrix = build_verified_candidate_matrix(
            [{"full_name": "Unknown Player", "professional_experience_years": None,
              "source_filenames": ["goalkeeper_unknown.txt"]}],
            {"min_experience_years": 5, "max_salary_eur": None,
             "relocation_north_required": False, "build_up_required": False,
             "calm_under_pressure_required": False, "position": None},
        )
        self.assertEqual(matrix["candidates"][0]["checks"]["experience"], "UNKNOWN")
        self.assertFalse(matrix["candidates"][0]["all_mandatory_pass"])

    def test_exact_match_false_when_any_fail(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_yossi_levi.txt", YOSSI_PROFILE),
            ]),
            extract_recruitment_requirements(
                "Goalkeeper willing to relocate north with at least 5 years"
            ),
        )
        self.assertFalse(matrix["candidates"][0]["all_mandatory_pass"])

    def test_prompt_includes_verified_matrix(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE),
            ]),
            extract_recruitment_requirements("at least 5 years up to 80,000 EUR"),
        )
        prompt = format_verified_matrix_for_prompt(matrix)
        self.assertIn("VERIFIED REQUIREMENT MATRIX", prompt)
        self.assertIn("Daniel Cohen", prompt)
        self.assertIn("experience_status: PASS", prompt)

    def test_prompt_instructs_no_arithmetic_redo(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE),
            ]),
            extract_recruitment_requirements("at least 5 years"),
        )
        prompt = format_verified_matrix_for_prompt(matrix)
        self.assertIn("Do not redo arithmetic", prompt)

    def test_validator_rejects_six_years_not_meeting_five(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE),
            ]),
            extract_recruitment_requirements("at least 5 years"),
        )
        ok, reason = validate_answer_against_verified_matrix(
            "Daniel Cohen has 6 years, which does not meet the required minimum of 5 years.",
            matrix,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "matrix_contradiction")

    def test_validator_rejects_ninety_within_eighty(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_omer_azulay.txt", OMER_PROFILE),
            ]),
            extract_recruitment_requirements("up to 80,000 EUR"),
        )
        ok, reason = validate_answer_against_verified_matrix(
            "Omer Azulay expects 90,000 EUR, which is within the maximum budget of 80,000 EUR.",
            matrix,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "matrix_contradiction")

    def test_matrix_contradiction_triggers_one_retry(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        uri_base = f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}"
        engine._runtime_client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "content": {"text": DANIEL_PROFILE},
                    "score": 0.95,
                    "location": {"s3Location": {"uri": f"{uri_base}player_cvs/goalkeeper_daniel_cohen.txt"}},
                },
            ]
        }
        engine._bedrock_client.converse.side_effect = [
            _converse_response(
                "Daniel Cohen has 6 years, which does not meet the required minimum of 5 years."
            ),
            _converse_response(
                "Daniel Cohen has 6 years of experience, which meets the minimum of 5 years."
            ),
        ]
        question = "Which goalkeeper has at least 5 years of experience?"
        result = engine.answer(question)
        self.assertFalse(result["refused"])
        self.assertIn("Daniel Cohen", result["answer"])
        self.assertEqual(engine._bedrock_client.converse.call_count, 2)

    def test_matrix_retry_fixes_contradiction_accepted(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _retrieve_payload(DANIEL_PROFILE)
        engine._bedrock_client.converse.side_effect = [
            _converse_response(
                "Daniel Cohen has 6 years and does not meet the minimum of 5 years."
            ),
            _converse_response(
                "Daniel Cohen has 6 years and meets the minimum of 5 years."
            ),
        ]
        result = engine.answer("Which goalkeeper has at least 5 years of experience?")
        self.assertFalse(result["refused"])

    def test_matrix_retry_still_contradicts_refused(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _retrieve_payload(DANIEL_PROFILE)
        bad = "Daniel Cohen has 6 years, which does not meet the required minimum of 5 years."
        engine._bedrock_client.converse.side_effect = [
            _converse_response(bad),
            _converse_response(bad),
        ]
        result = engine.answer("Which goalkeeper has at least 5 years of experience?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "matrix_contradiction")

    def test_no_unbounded_retries(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _retrieve_payload(DANIEL_PROFILE)
        bad = "Daniel Cohen has 6 years, which does not meet the required minimum of 5 years."
        vague = "The strongest candidate fits build-up play."
        engine._bedrock_client.converse.side_effect = [
            _converse_response(bad),
            _converse_response(bad),
            _converse_response(vague),
            _converse_response(vague),
        ]
        engine.answer("Which goalkeeper has at least 5 years of experience?")
        self.assertLessEqual(engine._bedrock_client.converse.call_count, 3)


class UIPolishTests(unittest.TestCase):
    """Sidebar dedup, main_source selection, and exact-match prompt polish."""

    def test_canonical_display_filename_strips_timestamp(self):
        self.assertEqual(
            canonical_display_filename("goalkeeper_daniel_cohen_20260531_183000.txt"),
            "goalkeeper_daniel_cohen.txt",
        )

    def test_sidebar_dedup_collapses_timestamped_cv_versions(self):
        docs = [
            _aws_doc("goalkeeper_daniel_cohen.txt", last_modified="2026-05-31T17:00:00"),
            _aws_doc("goalkeeper_daniel_cohen_20260531_183000.txt", last_modified="2026-05-31T18:30:00"),
            _aws_doc("goalkeeper_daniel_cohen_20260531_184500.txt", last_modified="2026-05-31T18:45:00"),
        ]
        display, raw_count = deduplicate_documents_for_display(docs)
        self.assertEqual(raw_count, 3)
        self.assertEqual(len(display), 1)
        self.assertEqual(display[0]["display_name"], "goalkeeper_daniel_cohen.txt")

    def test_different_cvs_remain_distinct(self):
        docs = [
            _aws_doc("goalkeeper_daniel_cohen.txt"),
            _aws_doc("goalkeeper_yossi_levi.txt"),
            _aws_doc("goalkeeper_omer_azulay.txt"),
            _aws_doc("goalkeeper_marco_silva.txt"),
        ]
        display, raw_count = deduplicate_documents_for_display(docs)
        self.assertEqual(raw_count, 4)
        self.assertEqual(len(display), 4)
        names = {doc["display_name"] for doc in display}
        self.assertEqual(names, {
            "goalkeeper_daniel_cohen.txt",
            "goalkeeper_yossi_levi.txt",
            "goalkeeper_omer_azulay.txt",
            "goalkeeper_marco_silva.txt",
        })

    def test_scouting_report_not_collapsed_into_cv(self):
        docs = [
            _aws_doc("goalkeeper_daniel_cohen.txt"),
            _aws_doc(
                "goalkeeper_daniel_cohen_report.txt",
                category="SCOUT REPORT",
            ),
        ]
        display, _ = deduplicate_documents_for_display(docs)
        self.assertEqual(len(display), 2)
        names = {doc["display_name"] for doc in display}
        self.assertIn("goalkeeper_daniel_cohen.txt", names)
        self.assertIn("goalkeeper_daniel_cohen_report.txt", names)

    def test_main_source_recommendation_prefers_recommended_cv(self):
        sources = [
            _source_card("goalkeeper_omer_azulay_report.txt", OMER_PROFILE, 0.9),
            _source_card("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE, 0.4),
        ]
        answer = (
            "Daniel Cohen and Marco Silva meet all mandatory requirements. "
            "Based on scouting reports, Daniel Cohen is the preferred candidate because..."
        )
        main = select_main_source(
            sources,
            answer=answer,
            question="Who is the most suitable goalkeeper?",
        )
        self.assertEqual(main["source"], "goalkeeper_daniel_cohen.txt")

    def test_main_source_factual_follow_up_prefers_referenced_cv(self):
        sources = [
            _source_card("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE, 0.9),
            _source_card("goalkeeper_marco_silva.txt", MARCO_PROFILE, 0.5),
        ]
        main = select_main_source(
            sources,
            answer="Marco Silva's salary expectation is 78,000 EUR per season.",
            question="ומה השכר של Marco Silva?",
        )
        self.assertEqual(main["source"], "goalkeeper_marco_silva.txt")

    def test_main_source_fallback_highest_score(self):
        sources = [
            _source_card("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE, 0.3),
            _source_card("goalkeeper_yossi_levi.txt", YOSSI_PROFILE, 0.8),
        ]
        main = select_main_source(
            sources,
            answer="Both players have strong build-up ability.",
            question="Tell me about goalkeeper build-up play.",
        )
        self.assertEqual(main["source"], "goalkeeper_yossi_levi.txt")

    def test_supporting_sources_preserved_in_response_payload(self):
        sources = [
            _source_card("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE, 0.8),
            _source_card("goalkeeper_marco_silva.txt", MARCO_PROFILE, 0.7),
        ]
        main = select_main_source(
            sources,
            answer="Daniel Cohen is the preferred candidate.",
            question="Who is the most suitable goalkeeper?",
        )
        self.assertEqual(len(sources), 2)
        self.assertIsNotNone(main)
        self.assertIn(main["source"], {s["source"] for s in sources})

    def test_prefix_isolation_excludes_unrelated_main_source(self):
        sources = [
            {
                "text": "Course notes",
                "source": "Flask-lecture1.pdf",
                "score": 0.99,
                "s3_uri": f"s3://{SCOUT_BUCKET}/data/Flask-lecture1.pdf",
            },
            _source_card("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE, 0.4),
        ]
        main = select_main_source(
            sources,
            answer="Daniel Cohen is the preferred candidate.",
            question="Who is the most suitable goalkeeper?",
        )
        self.assertEqual(main["source"], "goalkeeper_daniel_cohen.txt")

    def test_verified_matrix_prompt_acknowledges_exact_matches(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE),
                _player_chunk("goalkeeper_marco_silva.txt", MARCO_PROFILE),
            ]),
            extract_recruitment_requirements(
                "Goalkeeper with at least 5 years, calm under pressure, "
                "good with his feet, willing to relocate north, up to 80,000 EUR"
            ),
        )
        prompt = format_verified_matrix_for_prompt(matrix)
        self.assertIn("Exact-match candidates", prompt)
        self.assertIn("Daniel Cohen", prompt)
        self.assertIn("Marco Silva", prompt)
        self.assertIn("acknowledge every exact-match candidate", prompt)

    def test_multiple_exact_matches_prompt_requires_both_names(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE),
                _player_chunk("goalkeeper_marco_silva.txt", MARCO_PROFILE),
            ]),
            extract_recruitment_requirements("at least 5 years up to 80,000 EUR"),
        )
        exact = [
            row["player_name"]
            for row in matrix["candidates"]
            if row["all_mandatory_pass"]
        ]
        self.assertEqual(set(exact), {"Daniel Cohen", "Marco Silva"})
        prompt = format_verified_matrix_for_prompt(matrix)
        self.assertIn("Do not invent tie-breakers", prompt)

    def test_insufficient_evidence_prompt_instructs_uncertainty(self):
        prompt = format_verified_matrix_for_prompt({
            "requirements": {"min_experience_years": 5},
            "candidates": [
                {"player_name": "Daniel Cohen", "all_mandatory_pass": True, "checks": {}, "raw_values": {}, "unmet_requirements": [], "unknown_requirements": [], "source_filenames": []},
                {"player_name": "Marco Silva", "all_mandatory_pass": True, "checks": {}, "raw_values": {}, "unmet_requirements": [], "unknown_requirements": [], "source_filenames": []},
            ],
            "has_active_requirements": True,
        })
        self.assertIn("do not justify a definitive preference", prompt)

    def test_trump_refusal_unchanged(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        result = engine.answer("מי זה דונלד טראמפ?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "out_of_domain")
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_HE)
        self.assertEqual(result.get("context") or [], [])

    def test_named_player_salary_follow_up_allowed_without_history(self):
        self.assertTrue(
            _is_question_in_scoutmatch_domain("ומה השכר של Marco Silva?", history=[])
        )
        self.assertFalse(
            _is_question_in_scoutmatch_domain("ומה השכר שלו?", history=[])
        )


class ExactMatchAcknowledgmentTests(unittest.TestCase):
    """Exact-match acknowledgment validation, retry, and deterministic fallback."""

    def setUp(self):
        self.matrix = _dual_exact_match_matrix()

    def test_exact_match_helper_returns_both_candidates(self):
        exact = get_exact_match_candidates(self.matrix)
        names = {row["player_name"] for row in exact}
        self.assertEqual(names, {"Daniel Cohen", "Marco Silva"})
        self.assertTrue(all(row["all_mandatory_pass"] for row in exact))

    def test_omission_when_only_daniel_mentioned_is_invalid(self):
        answer = (
            "Daniel Cohen meets all mandatory requirements with 6 years and 75,000 EUR."
        )
        ok, reason = validate_exact_match_acknowledgment(
            answer, self.matrix, RECRUITMENT_QUESTION_EN
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "exact_match_acknowledgment")

    def test_hebrew_name_variant_recognized(self):
        answer = (
            "דניאל כהן ומרקו סילבה עומדים בדרישות החובה. "
            "דניאל כהן נראה כמועמד מתאים."
        )
        ok, reason = validate_exact_match_acknowledgment(
            answer, self.matrix, RECRUITMENT_QUESTION_HE
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_english_name_recognized(self):
        answer = (
            "Daniel Cohen and Marco Silva meet all mandatory requirements. "
            "Both are suitable candidates."
        )
        ok, reason = validate_exact_match_acknowledgment(
            answer, self.matrix, RECRUITMENT_QUESTION_EN
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_build_up_pass_contradiction_invalid(self):
        answer = (
            "Daniel Cohen and Marco Silva are discussed. "
            "Marco Silva lacks build-up ability evidence."
        )
        ok, reason = validate_exact_match_acknowledgment(
            answer, self.matrix, RECRUITMENT_QUESTION_EN
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "exact_match_acknowledgment")

    def test_calm_under_pressure_pass_contradiction_invalid(self):
        answer = (
            "Daniel Cohen and Marco Silva are candidates. "
            "Marco Silva has insufficient evidence under pressure."
        )
        ok, reason = validate_exact_match_acknowledgment(
            answer, self.matrix, RECRUITMENT_QUESTION_EN
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "exact_match_acknowledgment")

    def test_valid_multi_match_answer_accepted(self):
        answer = (
            "Daniel Cohen and Marco Silva meet all mandatory requirements. "
            "Both are suitable candidates to consider."
        )
        ok, reason = validate_exact_match_acknowledgment(
            answer, self.matrix, RECRUITMENT_QUESTION_EN
        )
        self.assertTrue(ok)

    def test_preference_with_scouting_evidence_accepted(self):
        answer = (
            "Daniel Cohen and Marco Silva meet all mandatory requirements. "
            "Based on scouting reports, Daniel Cohen appears to be the preferred candidate, "
            "but Marco Silva is also a suitable option."
        )
        ok, reason = validate_exact_match_acknowledgment(
            answer, self.matrix, RECRUITMENT_QUESTION_EN
        )
        self.assertTrue(ok)

    def test_fallback_states_uncertainty_without_tie_breaker(self):
        fallback = build_safe_exact_match_fallback(self.matrix, RECRUITMENT_QUESTION_HE)
        self.assertIn("Daniel Cohen", fallback)
        self.assertIn("Marco Silva", fallback)
        self.assertIn("אין מספיק מידע", fallback)

    def test_fallback_hebrew_lists_verified_values(self):
        fallback = build_safe_exact_match_fallback(self.matrix, RECRUITMENT_QUESTION_HE)
        self.assertIn("75,000", fallback)
        self.assertIn("78,000", fallback)
        self.assertIn("ScoutMatch", fallback)

    def test_fallback_english_lists_verified_values(self):
        fallback = build_safe_exact_match_fallback(self.matrix, RECRUITMENT_QUESTION_EN)
        self.assertIn("Daniel Cohen", fallback)
        self.assertIn("Marco Silva", fallback)
        self.assertIn("75,000", fallback)
        self.assertIn("78,000", fallback)
        self.assertIn("definitive preference", fallback)

    def test_exact_match_retry_instruction_present(self):
        self.assertIn("exact-match candidate", EXACT_MATCH_ACKNOWLEDGMENT_RETRY_INSTRUCTION)
        self.assertIn("all_mandatory_pass=YES", EXACT_MATCH_ACKNOWLEDGMENT_RETRY_INSTRUCTION)

    def test_retry_once_then_accepted(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _dual_player_retrieve_payload()
        bad = (
            "Daniel Cohen is the most suitable goalkeeper with 6 years and 75,000 EUR."
        )
        good = (
            "Daniel Cohen and Marco Silva meet all mandatory requirements. "
            "Daniel Cohen is the preferred candidate based on scouting reports."
        )
        engine._bedrock_client.converse.side_effect = [
            _converse_response(bad),
            _converse_response(good),
        ]
        result = engine.answer(RECRUITMENT_QUESTION_EN)
        self.assertFalse(result["refused"])
        self.assertIn("Marco Silva", result["answer"])
        self.assertEqual(engine._bedrock_client.converse.call_count, 2)

    def test_retry_still_invalid_uses_deterministic_fallback(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _dual_player_retrieve_payload()
        bad = (
            "Daniel Cohen is the most suitable goalkeeper. "
            "Marco Silva lacks build-up ability and calm under pressure evidence."
        )
        engine._bedrock_client.converse.side_effect = [
            _converse_response(bad),
            _converse_response(bad),
        ]
        result = engine.answer(RECRUITMENT_QUESTION_EN)
        self.assertFalse(result["refused"])
        self.assertEqual(result["generation_mode"], "aws_kb_exact_match_fallback")
        self.assertIn("Daniel Cohen", result["answer"])
        self.assertIn("Marco Silva", result["answer"])
        self.assertIn("75,000", result["answer"])
        self.assertIn("78,000", result["answer"])

    def test_fallback_preserves_scoutmatch_source_cards(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _dual_player_retrieve_payload()
        bad = "Daniel Cohen is the most suitable goalkeeper."
        engine._bedrock_client.converse.side_effect = [
            _converse_response(bad),
            _converse_response(bad),
        ]
        result = engine.answer(RECRUITMENT_QUESTION_EN)
        sources = result.get("context") or []
        self.assertGreaterEqual(len(sources), 2)
        names = {item.get("source") for item in sources}
        self.assertIn("goalkeeper_daniel_cohen.txt", names)
        self.assertIn("goalkeeper_marco_silva.txt", names)
        for item in sources:
            self.assertTrue(
                _is_allowed_scoutmatch_source(item.get("s3_uri") or "")
            )

    def test_main_source_remains_recommendation_aware_after_fallback(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _dual_player_retrieve_payload()
        bad = "Daniel Cohen is the most suitable goalkeeper."
        engine._bedrock_client.converse.side_effect = [
            _converse_response(bad),
            _converse_response(bad),
        ]
        result = engine.answer(RECRUITMENT_QUESTION_EN)
        main = result.get("main_source") or {}
        self.assertIn(
            main.get("source"),
            {"goalkeeper_daniel_cohen.txt", "goalkeeper_marco_silva.txt"},
        )

    def test_out_of_domain_trump_unchanged(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        result = engine.answer("מי זה דונלד טראמפ?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "out_of_domain")
        self.assertEqual(result["answer"], config.REFUSAL_TEXT_HE)
        self.assertEqual(result.get("context") or [], [])


class MarcoParserTests(unittest.TestCase):
    """Narrative fallback parsing and Marco Silva matrix coverage."""

    def test_narrative_build_up_specialist(self):
        facts = _parse_facts_from_text("Profile notes: build-up goalkeeper specialist.")
        self.assertEqual(facts.get("build_up_ability"), "Strong")

    def test_narrative_build_up_back_passes(self):
        facts = _parse_facts_from_text(
            "Comfortable receiving back-passes under pressure from centre-backs."
        )
        self.assertEqual(facts.get("build_up_ability"), "Strong")

    def test_narrative_calm_composed_under_pressure(self):
        facts = _parse_facts_from_text("Observed as composed under pressure in matches.")
        self.assertEqual(facts.get("calm_under_pressure"), "Strong")

    def test_narrative_calm_composure_under_high_press(self):
        facts = _parse_facts_from_text("Shows composure under high press when pressed.")
        self.assertEqual(facts.get("calm_under_pressure"), "Strong")

    def test_ambiguous_prose_stays_unknown(self):
        facts = _parse_facts_from_text(
            "The team plays an attractive style of football with quick transitions."
        )
        self.assertIsNone(facts.get("build_up_ability"))
        self.assertIsNone(facts.get("calm_under_pressure"))

    def test_structured_field_precedence_over_narrative(self):
        text = (
            "Build-up Ability: Limited\n"
            "Profile also describes a build-up specialist under pressure."
        )
        facts = _parse_facts_from_text(text)
        self.assertEqual(facts.get("build_up_ability"), "Limited")

    def test_marco_compact_profile_parses_all_fields(self):
        facts = extract_verified_player_facts([
            _player_chunk("goalkeeper_marco_silva.txt", MARCO_PROFILE),
        ])[0]
        self.assertEqual(facts["full_name"], "Marco Silva")
        self.assertEqual(facts["professional_experience_years"], 7)
        self.assertEqual(facts["annual_salary_eur"], 78000)
        self.assertEqual(facts["relocation_north"], "YES")
        self.assertEqual(facts["build_up_ability"], "Strong")
        self.assertEqual(facts["calm_under_pressure"], "Strong")

    def test_marco_narrative_fallback_all_mandatory_pass(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_marco_silva.txt", MARCO_NARRATIVE_ONLY),
            ]),
            extract_recruitment_requirements(RECRUITMENT_QUESTION_HE),
        )
        marco = next(r for r in matrix["candidates"] if r["player_name"] == "Marco Silva")
        self.assertTrue(marco["all_mandatory_pass"])

    def test_daniel_and_marco_exact_matches(self):
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_daniel_cohen.txt", DANIEL_PROFILE),
                _player_chunk("goalkeeper_marco_silva.txt", MARCO_PROFILE),
            ]),
            extract_recruitment_requirements(RECRUITMENT_QUESTION_HE),
        )
        exact = get_exact_match_candidates(matrix)
        self.assertEqual(
            {row["player_name"] for row in exact},
            {"Daniel Cohen", "Marco Silva"},
        )

    def test_daniel_only_answer_invalid_when_both_exact_match(self):
        matrix = _dual_exact_match_matrix()
        ok, reason = validate_exact_match_acknowledgment(
            "Daniel Cohen is the most suitable goalkeeper with 6 years experience.",
            matrix,
            RECRUITMENT_QUESTION_HE,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "exact_match_acknowledgment")

    def test_persistent_daniel_only_triggers_fallback_with_both_exact(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        engine._runtime_client.retrieve.return_value = _dual_player_retrieve_payload()
        bad = "Daniel Cohen is the most suitable goalkeeper with 6 years and 75,000 EUR."
        engine._bedrock_client.converse.side_effect = [
            _converse_response(bad),
            _converse_response(bad),
        ]
        result = engine.answer(RECRUITMENT_QUESTION_HE)
        self.assertFalse(result["refused"])
        self.assertEqual(result["generation_mode"], "aws_kb_exact_match_fallback")
        self.assertIn("Daniel Cohen", result["answer"])
        self.assertIn("Marco Silva", result["answer"])


class LineEndingParserTests(unittest.TestCase):
    """CR/CRLF/LF and pipe-separated full-name parsing."""

    def test_cr_only_full_name(self):
        text = (
            "Full Name: Marco Silva\r"
            "Position: Goalkeeper (GK)\r"
            "Professional Experience: 7 years"
        )
        facts = _parse_facts_from_text(text)
        self.assertEqual(facts.get("full_name"), "Marco Silva")

    def test_crlf_full_name(self):
        text = "Full Name: Daniel Cohen\r\nPosition: Goalkeeper (GK)"
        facts = _parse_facts_from_text(text)
        self.assertEqual(facts.get("full_name"), "Daniel Cohen")

    def test_lf_full_name(self):
        text = "Full Name: Yossi Levi\nPosition: Goalkeeper (GK)"
        facts = _parse_facts_from_text(text)
        self.assertEqual(facts.get("full_name"), "Yossi Levi")

    def test_pipe_separated_compact_profile(self):
        text = "Full Name: Omer Azulay | Professional Experience: 8 years"
        facts = _parse_facts_from_text(text)
        self.assertEqual(facts.get("full_name"), "Omer Azulay")

    def test_cr_only_marco_preserves_facts(self):
        text = (
            "Full Name: Marco Silva\r"
            "Position: Goalkeeper (GK)\r"
            "Professional Experience: 7 years\r"
            "Annual Salary Expectation: 78,000 EUR\r"
            "Relocation Willingness: YES\r"
            "Build-up Ability: Strong\r"
            "Calmness Under Pressure: Strong"
        )
        facts = _parse_facts_from_text(text)
        self.assertEqual(facts.get("full_name"), "Marco Silva")
        self.assertEqual(facts.get("professional_experience_years"), 7)
        self.assertEqual(facts.get("annual_salary_eur"), 78000)
        self.assertEqual(facts.get("relocation_north"), "YES")
        self.assertEqual(facts.get("build_up_ability"), "Strong")
        self.assertEqual(facts.get("calm_under_pressure"), "Strong")

    def test_matrix_candidate_names_clean_with_cr_only_chunks(self):
        daniel_cr = (
            "Full Name: Daniel Cohen\r"
            "Position: Goalkeeper (GK)\r"
            "Years of Professional Experience: 6\r"
            "Annual Salary Expectation: 75,000 EUR\r"
            "Relocation Willingness: YES\r"
            "Build-up Ability: Strong\r"
            "Calmness Under Pressure: Strong"
        )
        marco_cr = (
            "Full Name: Marco Silva\r"
            "Position: Goalkeeper (GK)\r"
            "Professional Experience: 7 years\r"
            "Annual Salary Expectation: 78,000 EUR\r"
            "Relocation Willingness: YES\r"
            "Build-up Ability: Strong\r"
            "Calmness Under Pressure: Strong"
        )
        matrix = build_verified_candidate_matrix(
            extract_verified_player_facts([
                _player_chunk("goalkeeper_daniel_cohen.txt", daniel_cr),
                _player_chunk("goalkeeper_marco_silva.txt", marco_cr),
            ]),
            extract_recruitment_requirements(RECRUITMENT_QUESTION_HE),
        )
        names = {row["player_name"] for row in matrix["candidates"]}
        self.assertEqual(names, {"Daniel Cohen", "Marco Silva"})
        for row in matrix["candidates"]:
            self.assertNotIn("Position:", row["player_name"])
            self.assertNotIn("Professional Experience:", row["player_name"])


class NamedPlayerProfileTests(unittest.TestCase):
    def setUp(self):
        self.engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(self.engine)

    def _or_david_uri(self) -> str:
        return (
            f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/"
            "forward_or_david.txt"
        )

    def _amit_uri(self) -> str:
        return (
            f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/"
            "defender_amit_levy.txt"
        )

    def test_general_profile_question_is_in_domain(self):
        self.assertTrue(_is_question_in_scoutmatch_domain("Who is Or David?"))
        self.assertTrue(_is_named_player_profile_question("Tell me about Or David."))
        self.assertEqual(
            _extract_named_player_from_profile_question("Who is Amit Levy?"),
            "Amit Levy",
        )

    def test_profile_query_expansion_includes_football_terms(self):
        expanded = _expand_named_player_retrieval_query("Or David")
        self.assertIn("player profile", expanded.lower())
        self.assertIn("or_david", expanded.lower())
        self.assertIn("position", expanded.lower())

    def test_general_or_david_question_returns_grounded_profile(self):
        self.engine._runtime_client.retrieve.return_value = _retrieve_payload(
            OR_DAVID_PROFILE,
            uri=self._or_david_uri(),
            score=0.95,
        )
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Or David is a striker aged 26 who "
            "plays for Beitar Jerusalem with 6 years of professional experience."
        )
        result = self.engine.answer("Who is Or David?")
        self.assertFalse(result["refused"])
        self.assertIn("Or David", result["answer"])
        self.assertTrue(result["context"])

    def test_tell_me_about_or_david_returns_profile(self):
        self.engine._runtime_client.retrieve.return_value = _retrieve_payload(
            OR_DAVID_PROFILE,
            uri=self._or_david_uri(),
            score=0.93,
        )
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Or David is a striker with 6 years "
            "of professional experience and a salary expectation of 58,000 EUR."
        )
        result = self.engine.answer("Tell me about Or David.")
        self.assertFalse(result["refused"])
        self.assertIn("Or David", result["answer"])

    def test_specific_position_question_still_works(self):
        self.engine._runtime_client.retrieve.return_value = _retrieve_payload(
            OR_DAVID_PROFILE,
            uri=self._or_david_uri(),
            score=0.94,
        )
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Or David's position is Striker (ST)."
        )
        result = self.engine.answer("What is Or David's position?")
        self.assertFalse(result["refused"])
        self.assertIn("Striker", result["answer"])

    def test_amit_levy_general_profile_question(self):
        self.engine._runtime_client.retrieve.return_value = _retrieve_payload(
            AMIT_LEVY_PROFILE,
            uri=self._amit_uri(),
            score=0.92,
        )
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Based on the uploaded documents, Amit Levy is a centre-back aged 25 "
            "with 5 years of professional experience."
        )
        result = self.engine.answer("Who is Amit Levy?")
        self.assertFalse(result["refused"])
        self.assertIn("Amit Levy", result["answer"])

    def test_unknown_player_question_refuses(self):
        self.engine._runtime_client.retrieve.return_value = {"retrievalResults": []}
        result = self.engine.answer("Who is Unknown Player?")
        self.assertTrue(result["refused"])

    def test_out_of_domain_still_refuses(self):
        engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(engine)
        result = engine.answer("Who is Donald Trump?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "out_of_domain")

    def test_session_isolation_blocks_other_session_uri(self):
        other_uri = (
            f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}sessions/other-session/or_david.txt"
        )
        self.assertFalse(_is_allowed_session_source(other_uri, TEST_SESSION_ID))


class HebrewPlayerProfileTests(unittest.TestCase):
    def setUp(self):
        self.engine = AWSKnowledgeBaseEngine()
        _prepare_engine_with_mocks(self.engine)

    def _or_david_uri(self) -> str:
        return (
            f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/"
            "forward_or_david.txt"
        )

    def _luca_uri(self) -> str:
        return (
            f"s3://{SCOUT_BUCKET}/{SCOUT_PREFIX}sessions/{TEST_SESSION_ID}/"
            "midfielder_luca_romano.txt"
        )

    def test_hebrew_who_is_or_david_extracts_name(self):
        self.assertEqual(
            _extract_named_player_from_profile_question("מי זה אור דוד?"),
            "אור דוד",
        )

    def test_hebrew_who_he_is_or_david_extracts_name(self):
        self.assertEqual(
            _extract_named_player_from_profile_question("מי הוא אור דוד?"),
            "אור דוד",
        )

    def test_hebrew_tell_me_about_or_david_extracts_name(self):
        self.assertEqual(
            _extract_named_player_from_profile_question("ספר לי על אור דוד"),
            "אור דוד",
        )

    def test_hebrew_position_question_extracts_name(self):
        self.assertEqual(
            _extract_named_player_from_profile_question("מה התפקיד של אור דוד?"),
            "אור דוד",
        )

    def test_hebrew_luca_romano_extracts_name(self):
        self.assertEqual(
            _extract_named_player_from_profile_question("מי זה לוקה רומאנו?"),
            "לוקה רומאנו",
        )

    def test_hebrew_normalization_to_english(self):
        self.assertEqual(
            _normalize_hebrew_profile_question_to_english("מי זה אור דוד?"),
            "Who is Or David?",
        )
        self.assertEqual(
            _normalize_hebrew_profile_question_to_english("מה התפקיד של אור דוד?"),
            "What is Or David's position?",
        )

    def test_hebrew_retrieval_queries_include_english_expansion(self):
        queries = _build_retrieval_queries("מי זה אור דוד?", "אור דוד")
        joined = " | ".join(queries).lower()
        self.assertIn("who is or david", joined)
        self.assertIn("player profile", joined)
        self.assertIn("or_david", joined)

    def test_hebrew_or_david_returns_grounded_profile(self):
        self.engine._runtime_client.retrieve.return_value = _retrieve_payload(
            OR_DAVID_PROFILE,
            uri=self._or_david_uri(),
            score=0.95,
        )
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "אור דוד הוא חלוץ בן 26 שמשחק בבית\"ר ירושלים עם 6 שנות ניסיון מקצועי."
        )
        result = self.engine.answer("מי זה אור דוד?")
        self.assertFalse(result["refused"])
        self.assertIn("אור דוד", result["answer"])
        self.assertTrue(result["context"])
        prompt = self.engine._bedrock_client.converse.call_args.kwargs["system"][0]["text"]
        self.assertIn("Hebrew", prompt)

    def test_hebrew_position_question_returns_grounded_profile(self):
        self.engine._runtime_client.retrieve.return_value = _retrieve_payload(
            OR_DAVID_PROFILE,
            uri=self._or_david_uri(),
            score=0.94,
        )
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "לפי המסמכים, התפקיד של אור דוד הוא חלוץ (ST)."
        )
        result = self.engine.answer("מה התפקיד של אור דוד?")
        self.assertFalse(result["refused"])
        self.assertIn("אור דוד", result["answer"])

    def test_hebrew_luca_romano_returns_grounded_profile(self):
        luca_profile = (
            "Full Name: Luca Romano\n"
            "Position: Attacking Midfielder (AM)\n"
            "Age: 24\n"
            "Current Club: Maccabi Haifa\n"
        )
        self.engine._runtime_client.retrieve.return_value = _retrieve_payload(
            luca_profile,
            uri=self._luca_uri(),
            score=0.93,
        )
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "לוקה רומאנו הוא קשר התקפי בן 24 שמשחק במכבי חיפה."
        )
        result = self.engine.answer("מי זה לוקה רומאנו?")
        self.assertFalse(result["refused"])
        self.assertIn("לוקה רומאנו", result["answer"])

    def test_english_equivalent_still_works(self):
        self.engine._runtime_client.retrieve.return_value = _retrieve_payload(
            OR_DAVID_PROFILE,
            uri=self._or_david_uri(),
            score=0.95,
        )
        self.engine._bedrock_client.converse.return_value = _converse_response(
            "Or David is a 26-year-old striker who plays for Beitar Jerusalem."
        )
        result = self.engine.answer("Who is Or David?")
        self.assertFalse(result["refused"])
        self.assertIn("Or David", result["answer"])
        prompt = self.engine._bedrock_client.converse.call_args.kwargs["system"][0]["text"]
        self.assertIn("English", prompt)

    def test_unknown_hebrew_player_refuses(self):
        self.engine._runtime_client.retrieve.return_value = {"retrievalResults": []}
        result = self.engine.answer("מי זה אלכס מוריס?")
        self.assertTrue(result["refused"])
        self.assertIn("אין", result["answer"])

    def test_hebrew_out_of_domain_refuses(self):
        result = self.engine.answer("מהי בירת צרפת?")
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason"], "out_of_domain")

    def test_hebrew_answer_language_instruction(self):
        instruction = _language_instruction_for_question("מי זה אור דוד?")
        self.assertIn("Hebrew", instruction)

    def test_english_player_name_mapping(self):
        self.assertEqual(_english_player_name("אור דוד"), "Or David")
        self.assertEqual(_english_player_name("לוקה רומאנו"), "Luca Romano")


if __name__ == "__main__":
    unittest.main(verbosity=2)
