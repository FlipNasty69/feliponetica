import unittest
from unittest.mock import patch

from features.feliponetica_local_api import app


class FeliponeticaLocalApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_convert_returns_pollito_plain_text(self):
        response = self.client.post(
            "/convert",
            data="excited",
            content_type="text/plain; charset=utf-8",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/plain")
        self.assertEqual(response.get_data(as_text=True), "ek-sai-ted")

    def test_convert_calls_the_pollito_converter_with_input(self):
        with patch(
            "features.feliponetica_local_api.convert_to_feliponetica_pollito",
            return_value="End, jelo!",
        ) as convert_text:
            response = self.client.post(
                "/convert",
                data="And, hello!",
                content_type="text/plain; charset=utf-8",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "End, jelo!")
        convert_text.assert_called_once_with("And, hello!")

    def test_convert_requires_plain_text(self):
        response = self.client.post("/convert", json={"text": "hello"})

        self.assertEqual(response.status_code, 415)
        self.assertIn("Content-Type", response.get_data(as_text=True))

    def test_convert_rejects_empty_text(self):
        response = self.client.post(
            "/convert",
            data=" \t\n",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Text is required", response.get_data(as_text=True))

    def test_convert_rejects_invalid_utf8(self):
        response = self.client.post(
            "/convert",
            data=b"\xff",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("UTF-8", response.get_data(as_text=True))

    def test_convert_rejects_payloads_over_64_kb(self):
        response = self.client.post(
            "/convert",
            data="x" * (64 * 1024 + 1),
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 413)
        self.assertIn("64 KB", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
