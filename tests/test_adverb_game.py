import unittest

from app import app
from games import adverb_game


class AdverbGameRoutesTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.previous_cache = adverb_game._game_data_cache
        adverb_game._game_data_cache = None

    def tearDown(self):
        adverb_game._game_data_cache = self.previous_cache

    def test_course_and_games_dashboard_link_to_adverb_game(self):
        with self.client.session_transaction() as user_session:
            user_session["username"] = "student@example.com"
            user_session["role"] = "enrolled student"
        course = self.client.get("/course")
        games = self.client.get("/games")

        self.assertEqual(course.status_code, 200)
        self.assertIn(b"Play Adverb Game", course.data)
        self.assertIn(b'href="/adverb-game/game"', course.data)
        self.assertEqual(games.status_code, 200)
        self.assertIn(b"Adverb Adventure", games.data)
        self.assertIn(b'href="/adverb-game/game"', games.data)

    def test_game_page_loads_workbook_categories(self):
        response = self.client.get("/adverb-game/game")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Meaning Match", response.data)
        self.assertIn(b"Sentence Spotter", response.data)
        self.assertIn(b"Manner", response.data)

    def test_meaning_round_uses_workbook_choices(self):
        response = self.client.get("/adverb-game/api/round?mode=meaning&count=3")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["questions"]), 3)
        for question in payload["questions"]:
            self.assertEqual(len(question["choices"]), 4)
            self.assertIn(question["answer"], question["choices"])
            self.assertIn(" ", question["prompt"])

    def test_placement_round_has_true_and_false_challenges(self):
        response = self.client.get("/adverb-game/api/round?mode=placement&count=25")

        self.assertEqual(response.status_code, 200)
        questions = response.get_json()["questions"]
        self.assertEqual(len(questions), 25)
        self.assertEqual({type(question["answer"]) for question in questions}, {bool})
        self.assertTrue(all(question["sentence"].endswith((".", "?", "!")) for question in questions))

    def test_round_rejects_invalid_modes_and_categories(self):
        invalid_mode = self.client.get("/adverb-game/api/round?mode=other")
        invalid_category = self.client.get("/adverb-game/api/round?category=not-a-category")

        self.assertEqual(invalid_mode.status_code, 400)
        self.assertEqual(invalid_category.status_code, 400)
