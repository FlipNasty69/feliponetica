import unittest

from app import app


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
