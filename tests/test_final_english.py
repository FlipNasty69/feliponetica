import json
import os
import sqlite3
import tempfile
import unittest

from app import app, init_test_results_database, load_final_english_test


class FinalEnglishTestRoutes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "test-results.sqlite3")
        self.previous_database_path = app.config.get("TEST_RESULTS_DATABASE_PATH")
        app.config.update(
            TESTING=True,
            TEST_RESULTS_DATABASE_PATH=self.database_path,
        )
        init_test_results_database()
        self.client = app.test_client()

    def tearDown(self):
        if self.previous_database_path is None:
            app.config.pop("TEST_RESULTS_DATABASE_PATH", None)
        else:
            app.config["TEST_RESULTS_DATABASE_PATH"] = self.previous_database_path
        app.config["TESTING"] = False
        self.temp_dir.cleanup()

    def register(self):
        return self.client.post(
            "/tests/final-english/register",
            data={"name": "Test Taker", "email": "test@example.com"},
            follow_redirects=True,
        )

    def test_course_links_to_test_center_and_test_is_listed(self):
        self.client.post(
            "/login",
            data={"username": "felipe", "password": "felipe"},
        )
        course = self.client.get("/course")
        self.assertIn(b"Test Center", course.data)
        self.assertIn(b"/test-center", course.data)

        test_center = self.client.get("/test-center")
        self.assertIn(b"Final English Test", test_center.data)

    def test_registration_rejects_invalid_email(self):
        response = self.client.post(
            "/tests/final-english/register",
            data={"name": "Test Taker", "email": "not-an-email"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enter a valid email address.", response.data)
        self.assertEqual(
            self.client.get("/tests/final-english/take").status_code,
            302,
        )

    def test_registration_and_question_page_do_not_expose_answers(self):
        response = self.register()

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"question-text", response.data)
        self.assertNotIn(b"correct_answer", response.data)
        self.assertNotIn(b"correct-answer", response.data)

    def test_completed_report_is_private_and_available_to_admin(self):
        self.register()
        questions = load_final_english_test()
        answers = {
            question["id"]: question["correct_answer"]
            for question in questions
        }

        incomplete = self.client.post(
            "/tests/final-english/submit",
            json={},
        )
        self.assertEqual(incomplete.status_code, 400)
        invalid_answer = dict(answers)
        invalid_answer[questions[0]["id"]] = "Z"
        self.assertEqual(
            self.client.post("/tests/final-english/submit", json=invalid_answer).status_code,
            400,
        )

        response = self.client.post("/tests/final-english/submit", json=answers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"submitted": True})
        connection = sqlite3.connect(self.database_path)
        try:
            result = connection.execute(
                "SELECT name, email, score, question_count, report_json FROM test_results"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(result[:4], ("Test Taker", "test@example.com", 100, 100))
        report = json.loads(result[4])
        self.assertEqual(len(report), 100)
        self.assertTrue(all(question["is_correct"] for question in report))

        protected = self.client.get("/admin/test-results")
        self.assertNotIn(b"test@example.com", protected.data)
        self.assertEqual(protected.status_code, 200)
        login = self.client.post(
            "/admin/test-results",
            data={"password": "ifyouaintcheatinyouainttryin"},
        )
        self.assertEqual(login.status_code, 302)

        admin_results = self.client.get("/admin/test-results")
        self.assertIn(b"test@example.com", admin_results.data)
        self.assertIn(b"100 / 100", admin_results.data)
        self.assertEqual(admin_results.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
