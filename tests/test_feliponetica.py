import os
import unittest
from unittest.mock import patch

from app import app
from features.feliponetica import (
    convert_to_feliponetica,
    convert_to_feliponetica_pollito,
)


class FeliponeticaWordApiTests(unittest.TestCase):
    def setUp(self):
        self.previous_api_key = app.config.get("FELIPONETICA_WORD_API_KEY")
        self.previous_testing = app.config.get("TESTING", False)
        app.config.update(TESTING=True, FELIPONETICA_WORD_API_KEY="test-word-key")
        self.client = app.test_client()

    def tearDown(self):
        app.config["TESTING"] = self.previous_testing
        if self.previous_api_key is None:
            app.config.pop("FELIPONETICA_WORD_API_KEY", None)
        else:
            app.config["FELIPONETICA_WORD_API_KEY"] = self.previous_api_key

    def test_word_api_requires_a_valid_bearer_token(self):
        missing_key = self.client.post(
            "/api/feliponetica/word",
            json={"text": "hello"},
        )
        invalid_key = self.client.post(
            "/api/feliponetica/word",
            headers={"Authorization": "Bearer wrong-key"},
            json={"text": "hello"},
        )

        self.assertEqual(missing_key.status_code, 401)
        self.assertEqual(missing_key.get_json()["error"], "A valid bearer token is required.")
        self.assertEqual(invalid_key.status_code, 401)
        self.assertEqual(invalid_key.headers["WWW-Authenticate"], "Bearer")

    def test_word_api_returns_source_and_feliponetica_with_punctuation(self):
        text = "And, hello!\nCats-dogs."
        response = self.client.post(
            "/api/feliponetica/word",
            headers={"Authorization": "Bearer test-word-key"},
            json={"text": text},
        )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["text"], text)
        self.assertEqual(payload["dialect"], "pollito")
        self.assertTrue(payload["result"].startswith("End, "))
        self.assertIn("!\n", payload["result"])
        self.assertIn("-", payload["result"])
        self.assertTrue(payload["result"].endswith("."))
        self.assertEqual(
            payload["formatted_text"],
            f"{text}\r\n{payload['result']}",
        )

    def test_word_api_validates_payload(self):
        response = self.client.post(
            "/api/feliponetica/word",
            headers={"Authorization": "Bearer test-word-key"},
            json={"text": "hello", "dialect": "unsupported"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "dialect must be pollito or gallo",
        )

    def test_and_is_end_for_both_dialects_and_punctuation_is_preserved(self):
        self.assertEqual(convert_to_feliponetica("and"), "end")
        self.assertEqual(convert_to_feliponetica_pollito("And,"), "End,")
        self.assertEqual(convert_to_feliponetica("AND!"), "END!")
        self.assertEqual(
            convert_to_feliponetica_pollito("hello,\nworld!").count("\n"),
            1,
        )
        self.assertIn(
            "'",
            convert_to_feliponetica_pollito("don't stop, well-known!"),
        )

    def test_word_api_fails_closed_when_no_key_is_configured(self):
        app.config.pop("FELIPONETICA_WORD_API_KEY", None)
        with patch.dict(os.environ, {"FELIPONETICA_WORD_API_KEY": ""}):
            response = self.client.post(
                "/api/feliponetica/word",
                headers={"Authorization": "Bearer anything"},
                json={"text": "hello"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"],
            "The Word transcription API is not configured.",
        )


if __name__ == "__main__":
    unittest.main()
