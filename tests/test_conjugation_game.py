import unittest

from app import app


class ConjugationGameTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_game_offers_building_a_set_from_verb_ids(self):
        response = self.client.get("/verb_conjugation_game?guest=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Build a Verb Set by ID", response.data)
        self.assertIn(b"V00032 V00036 V00142 V00193", response.data)
        self.assertIn(b'id="id-verb-form"', response.data)
        response.close()

        engine = self.client.get("/static/scripts/conjugation_engine.js")
        self.assertEqual(engine.status_code, 200)
        self.assertIn(b"Build a set by ID", engine.data)
        self.assertIn(b"function findVerbIdField", engine.data)
        self.assertIn(b"requestedIds.map(id => verbsById.get(id))", engine.data)
        engine.close()

    def test_game_audio_uses_cloudflare_object_key_paths(self):
        engine = self.client.get("/static/scripts/conjugation_engine.js")

        self.assertEqual(engine.status_code, 200)
        self.assertIn(
            b'const audioRoot = "/static/audio/verb_conjugation/";',
            engine.data,
        )
        self.assertIn(b"/static/audio/game_feedback/correct_answer-", engine.data)
        self.assertIn(b"/static/audio/verb_conjugation/", engine.data)
        self.assertIn(b"pronunciation(?:%20| )audio", engine.data)
        engine.close()


if __name__ == "__main__":
    unittest.main()
