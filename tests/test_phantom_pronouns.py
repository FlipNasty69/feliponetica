import unittest
from unittest.mock import patch

from app import app
from games import phantom_pronouns


class PhantomPronounsRoutesTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_games_dashboard_links_to_phantom_pronouns(self):
        response = self.client.get("/games")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Phantom Pronouns", response.data)
        self.assertIn(b'href="/phantom-pronouns/game"', response.data)

    def test_phantom_pronouns_game_page_loads(self):
        response = self.client.get("/phantom-pronouns/game")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Phantom Pronouns", response.data)

    def test_level_one_loads_verbs_from_workbook(self):
        previous_cache = phantom_pronouns._level1_cache
        try:
            phantom_pronouns._level1_cache = None
            data = phantom_pronouns._get_level1_data()
        finally:
            phantom_pronouns._level1_cache = previous_cache

        self.assertGreaterEqual(len(data["verbs"]), 80)
        self.assertIn("saw", {verb["gloss"] for verb in data["verbs"]})
        self.assertEqual(
            {verb["schema"] for verb in data["verbs"] if verb["gloss"] == "saw"},
            {1, 3, 4},
        )

    def test_level_one_uses_referenced_schema_forms_and_clitics(self):
        previous_cache = phantom_pronouns._level1_cache
        try:
            phantom_pronouns._level1_cache = None
            data = phantom_pronouns._get_level1_data()
        finally:
            phantom_pronouns._level1_cache = previous_cache

        saw = next(
            verb for verb in data["verbs"]
            if verb["gloss"] == "saw" and verb["schema"] == 1
        )
        self.assertEqual(saw["conj"]["i"], "vi")
        self.assertEqual(saw["phonetic"], "sa")
        self.assertEqual(saw["clitic_reference"], "s2")
        self.assertIn(("i", "you"), data["schemas"][1])
        self.assertNotIn(("i", "me"), data["schemas"][1])
        self.assertEqual(data["clitics"]["them"]["s1"], "les")
        self.assertEqual(data["clitics"]["them"]["s2"], "los")
        self.assertEqual(
            {object_id for subject_id, object_id in data["schemas"][5]
             if subject_id == "i"},
            {"it"},
        )

        previous_cache = phantom_pronouns._level1_cache
        try:
            phantom_pronouns._level1_cache = data
            with patch.object(
                phantom_pronouns.random,
                "choice",
                side_effect=lambda choices: next(
                    (choice for choice in choices
                     if isinstance(choice, dict) and choice.get("gloss") == "saw"),
                    choices[0],
                ),
            ):
                exercise = phantom_pronouns._build_level1_exercise()
        finally:
            phantom_pronouns._level1_cache = previous_cache

        self.assertEqual(exercise["spanish_prompt"], "Te vi.")
        self.assertEqual(exercise["correct_subject_id"], "i")
        self.assertEqual(exercise["correct_object_id"], "you")
        self.assertEqual(exercise["verb_phonetic"], "[ sa ]")

    def test_api_serves_ten_level_one_exercises_only(self):
        levels_response = self.client.get("/phantom-pronouns/api/levels")
        exercise_response = self.client.get(
            "/phantom-pronouns/api/exercise-set?level=1"
        )
        unavailable_level_response = self.client.get(
            "/phantom-pronouns/api/exercise-set?level=2"
        )

        self.assertEqual(levels_response.status_code, 200)
        self.assertEqual([level["id"] for level in levels_response.get_json()], [1])
        self.assertEqual(exercise_response.status_code, 200)
        self.assertEqual(len(exercise_response.get_json()), 10)
        self.assertEqual(unavailable_level_response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
