"""Unit tests for baseline club knowledge parsing and deterministic answers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import config
import database
from baseline_club_knowledge import (
    build_baseline_club_answer,
    build_budget_combination_answer,
    build_below_striker_recommendation_answer,
    build_immediate_right_back_answer,
    classify_baseline_question_intent,
    is_baseline_club_question,
    is_budget_combination_question,
    parse_baseline_file_content,
    parse_demo_candidate_content,
    is_baseline_only_question,
)


ROOT = Path(__file__).resolve().parent.parent
BASELINE_DIR = ROOT / "sample_scout_data" / "baseline"


class BaselineParsingTests(unittest.TestCase):
    def test_club_profile_parses_season_goal(self):
        text = (BASELINE_DIR / "club_profile.txt").read_text(encoding="utf-8")
        facts = parse_baseline_file_content(text, "club_profile.txt")
        self.assertIn("top four", (facts.get("season_goal_short") or facts.get("season_goal", "")).lower())

    def test_transfer_budget_parses_combined_total(self):
        text = (BASELINE_DIR / "transfer_budget.txt").read_text(encoding="utf-8")
        facts = parse_baseline_file_content(text, "transfer_budget.txt")
        self.assertEqual(facts.get("combined_budget_eur"), 100000)

    def test_fixture_congestion_parses_matches(self):
        text = (BASELINE_DIR / "fixture_congestion_note.txt").read_text(encoding="utf-8")
        facts = parse_baseline_file_content(text, "fixture_congestion_note.txt")
        self.assertEqual(facts.get("fixture_congestion_matches"), 5)
        self.assertEqual(facts.get("fixture_congestion_days"), 18)


class BaselineAnswerTests(unittest.TestCase):
    def setUp(self):
        self.club_facts = {
            "season_goal_short": "finish in the top four",
            "combined_budget_eur": 100000,
            "urgent_positions": ["Right Back", "Attacking Midfielder", "Forward"],
            "fixture_congestion_matches": 5,
            "fixture_congestion_days": 18,
        }

    def test_club_goal_answer(self):
        answer = build_baseline_club_answer("What is the club's main goal this season?", self.club_facts)
        self.assertIn("top four", (answer or "").lower())

    def test_budget_answer(self):
        answer = build_baseline_club_answer("What is the club's transfer budget?", self.club_facts)
        self.assertIn("100,000 EUR", answer or "")

    def test_hebrew_budget_question_is_baseline_only(self):
        self.assertTrue(is_baseline_only_question("מהו תקציב השכר הכולל להחתמות חדשות?"))

    def test_hebrew_urgent_positions_canonical(self):
        self.assertEqual(
            classify_baseline_question_intent("אילו עמדות דורשות חיזוק דחוף?"),
            "urgent_positions",
        )
        answer = build_baseline_club_answer(
            "אילו עמדות דורשות חיזוק דחוף?",
            self.club_facts,
        )
        self.assertIn("מגן ימני", answer or "")
        self.assertIn("קשר התקפי", answer or "")
        self.assertIn("חלוץ", answer or "")

    def test_hebrew_urgent_positions_variants(self):
        variants = [
            "איזה עמדות צריך לחזק בדחיפות?",
            "באילו עמדות הקבוצה צריכה חיזוק?",
            "מהן העמדות הדחופות לחיזוק?",
        ]
        for question in variants:
            with self.subTest(question=question):
                self.assertEqual(classify_baseline_question_intent(question), "urgent_positions")
                answer = build_baseline_club_answer(question, self.club_facts)
                self.assertIn("מגן ימני", answer or "")

    def test_hebrew_immediate_availability_canonical(self):
        self.assertEqual(
            classify_baseline_question_intent("למה זמינות מיידית חשובה?"),
            "immediate_availability",
        )
        answer = build_baseline_club_answer("למה זמינות מיידית חשובה?", self.club_facts)
        self.assertIn("5", answer or "")
        self.assertIn("18", answer or "")

    def test_hebrew_immediate_availability_variants(self):
        for question in (
            "מדוע זמינות מיידית חשובה?",
            "למה חשוב שהשחקן יהיה זמין מיד?",
            "למה צריך שחקן שיכול להצטרף מיד?",
        ):
            with self.subTest(question=question):
                self.assertEqual(classify_baseline_question_intent(question), "immediate_availability")
                answer = build_baseline_club_answer(question, self.club_facts)
                self.assertIn("5", answer or "")

    def test_budget_combination_ron_and_tal(self):
        players = [
            {"full_name": "Ron Ben Ari", "annual_salary_eur": 43000},
            {"full_name": "Tal Raz", "annual_salary_eur": 50000},
        ]
        answer = build_budget_combination_answer(
            "Can the club afford both Ron Ben Ari and Tal Raz?",
            players,
            self.club_facts,
        )
        self.assertIn("93,000 EUR", answer or "")
        self.assertIn("100,000 EUR", answer or "")

    def test_hebrew_budget_combination_variants(self):
        players = [
            {"full_name": "Ron Ben Ari", "annual_salary_eur": 43000},
            {"full_name": "Tal Raz", "annual_salary_eur": 50000},
        ]
        variants = [
            "האם המועדון יכול להרשות לעצמו גם את רון בן ארי וגם את טל רז?",
            "האם הקבוצה יכולה להרשות לעצמה להחתים את רון בן ארי ואת טל רז?",
            "האם התקציב מספיק לרון בן ארי ולטל רז?",
            "האם אפשר להחתים יחד את רון בן ארי ואת טל רז?",
            "האם אפשר לצרף את רון בן ארי ואת טל רז במסגרת התקציב?",
        ]
        for question in variants:
            with self.subTest(question=question):
                self.assertTrue(is_budget_combination_question(question))
                answer = build_budget_combination_answer(question, players, self.club_facts)
                self.assertIn("93,000 EUR", answer or "")
                self.assertIn("100,000 EUR", answer or "")

    def test_below_striker_recommendation_tal_raz(self):
        players = [
            {
                "full_name": "Tal Raz",
                "position": "Attacking Midfielder / Second Striker",
                "annual_salary_eur": 50000,
                "availability": "Immediate",
                "vision": 9,
                "creativity": 9,
                "key_passing": 8,
            },
            {
                "full_name": "Eyal Mor",
                "position": "Attacking Midfielder",
                "annual_salary_eur": 45000,
                "vision": 7,
            },
        ]
        answer = build_below_striker_recommendation_answer(
            "Who is the best fit to play below the striker?",
            players,
            self.club_facts,
        )
        self.assertIn("Tal Raz", answer or "")

    def test_immediate_right_back_changes_with_availability_update(self):
        before = [
            {"full_name": "Ron Ben Ari", "position": "Right Back", "availability": "Immediate", "annual_salary_eur": 43000},
            {"full_name": "Dor Levi", "position": "Right Back", "availability": "Immediate", "annual_salary_eur": 47000},
        ]
        after = [
            {"full_name": "Ron Ben Ari", "position": "Right Back", "availability": "March 2026", "annual_salary_eur": 43000},
            {"full_name": "Dor Levi", "position": "Right Back", "availability": "Immediate", "annual_salary_eur": 47000},
        ]
        ans_before = build_immediate_right_back_answer(
            "Who is the best immediate option for right back?",
            before,
        )
        ans_after = build_immediate_right_back_answer(
            "Who is the best immediate option for right back?",
            after,
        )
        self.assertIn("Ron Ben Ari", ans_before or "")
        self.assertIn("Dor Levi", ans_after or "")


class BaselineRegistryTests(unittest.TestCase):
    def test_baseline_documents_table_migration(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        orig = database.DB_PATH
        try:
            database.DB_PATH = tmp.name
            database._local.conn = None
            database.init_db()
            doc = database.upsert_baseline_document(
                "production",
                "scoutmatch/knowledge-base/baseline/production/club_profile.txt",
                "club_profile.txt",
                category="Club Profile",
                content_hash="abc",
                parsed_facts={"combined_budget_eur": 100000},
            )
            self.assertEqual(doc["display_name"], "club_profile.txt")
            rows = database.list_baseline_documents("production")
            self.assertEqual(len(rows), 1)
            facts = database.aggregate_baseline_club_facts("production")
            self.assertEqual(facts.get("combined_budget_eur"), 100000)
        finally:
            conn = getattr(database._local, "conn", None)
            if conn is not None:
                conn.close()
                database._local.conn = None
            database.DB_PATH = orig


class DemoCandidateParseTests(unittest.TestCase):
    def test_demo_manifest_exists(self):
        manifest = json.loads(
            (ROOT / "sample_scout_data" / "demo_candidates" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(manifest.get("files") or []), 6)

    def test_tal_raz_docx_fields(self):
        path = ROOT / "sample_scout_data" / "demo_candidates" / "tal_raz_cv.docx"
        if not path.is_file():
            self.skipTest("demo fixtures not generated")
        import io
        import zipfile

        with zipfile.ZipFile(path) as archive:
            text = archive.read("word/document.xml").decode("utf-8", errors="ignore")
        import re
        text = re.sub(r"<[^>]+>", " ", text)
        facts = parse_demo_candidate_content(text, "tal_raz_cv.docx")
        self.assertEqual(facts.get("full_name"), "Tal Raz")
        self.assertEqual(facts.get("annual_salary_eur"), 50000)
        self.assertEqual(facts.get("vision"), 9)


if __name__ == "__main__":
    unittest.main()
