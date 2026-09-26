import unittest

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

        self.assertGreater(
            len(data["verbs"]), len(phantom_pronouns._FALLBACK_LEVEL1_VERBS)
        )
        self.assertIn("saw", {verb["gloss"] for verb in data["verbs"]})

    def test_phantom_pronouns_api_routes_load(self):
        levels_response = self.client.get("/phantom-pronouns/api/levels")
        exercise_response = self.client.get(
            "/phantom-pronouns/api/exercise-set?level=1&count=1"
        )

        self.assertEqual(levels_response.status_code, 200)
        self.assertEqual(len(levels_response.get_json()), 7)
        self.assertEqual(exercise_response.status_code, 200)
        self.assertEqual(len(exercise_response.get_json()), 1)


if __name__ == "__main__":
    unittest.main()
