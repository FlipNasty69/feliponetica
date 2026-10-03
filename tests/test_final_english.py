import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from app import (
    app,
    init_student_database,
    init_test_results_database,
    load_final_english_test,
    test_results_database_path,
)
from werkzeug.security import check_password_hash
from word_order.storage import connect_database as connect_word_order_database


class FinalEnglishTestRoutes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "test-results.sqlite3")
        self.student_database_path = os.path.join(self.temp_dir.name, "students.sqlite3")
        self.word_order_database_path = os.path.join(self.temp_dir.name, "word-order.sqlite3")
        self.previous_database_path = app.config.get("TEST_RESULTS_DATABASE_PATH")
        self.previous_student_database_path = app.config.get("STUDENT_DATABASE_PATH")
        self.previous_word_order_database_path = app.config.get("WORD_ORDER_DATABASE")
        app.config.update(
            TESTING=True,
            TEST_RESULTS_DATABASE_PATH=self.database_path,
            STUDENT_DATABASE_PATH=self.student_database_path,
            WORD_ORDER_DATABASE=self.word_order_database_path,
        )
        init_student_database()
        init_test_results_database()
        self.client = app.test_client()

    def tearDown(self):
        if self.previous_database_path is None:
            app.config.pop("TEST_RESULTS_DATABASE_PATH", None)
        else:
            app.config["TEST_RESULTS_DATABASE_PATH"] = self.previous_database_path
        if self.previous_student_database_path is None:
            app.config.pop("STUDENT_DATABASE_PATH", None)
        else:
            app.config["STUDENT_DATABASE_PATH"] = self.previous_student_database_path
        if self.previous_word_order_database_path is None:
            app.config.pop("WORD_ORDER_DATABASE", None)
        else:
            app.config["WORD_ORDER_DATABASE"] = self.previous_word_order_database_path
        app.config["TESTING"] = False
        self.temp_dir.cleanup()

    def register(self, email="test@example.com", password="student-password"):
        return self.client.post(
            "/register",
            data={
                "name": "Test",
                "last_name": "Taker",
                "email": email,
                "password": password,
                "next": "/tests/final-english/register",
            },
        )

    def test_test_results_database_can_use_configured_persistent_path(self):
        configured_path = os.path.join(self.temp_dir.name, "persistent", "results.sqlite3")
        with patch.dict(os.environ, {"TEST_RESULTS_DATABASE_PATH": configured_path}):
            app.config.pop("TEST_RESULTS_DATABASE_PATH", None)
            self.assertEqual(test_results_database_path(), configured_path)
        app.config["TEST_RESULTS_DATABASE_PATH"] = self.database_path

    def approve_assessment(self, email="test@example.com"):
        with closing(sqlite3.connect(self.student_database_path)) as connection, connection:
            user_id = connection.execute(
                "SELECT id FROM student_users WHERE email = ?",
                (email,),
            ).fetchone()[0]
        login = self.client.post(
            "/admin/test-results",
            data={"password": "ifyouaintcheatinyouainttryin"},
        )
        self.assertEqual(login.status_code, 302)
        return self.client.post(
            f"/admin/test-results/users/{user_id}/approvals",
            data={"category": "assessment", "approved": "1"},
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

    def test_account_registration_rejects_invalid_email(self):
        response = self.client.post(
            "/register",
            data={
                "name": "Test",
                "last_name": "Taker",
                "email": "not-an-email",
                "password": "student-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enter a valid email address.", response.data)

    def test_registered_account_can_sign_in_with_its_hashed_password(self):
        password = "account-secret"
        self.register(password=password)
        self.client.get("/logout")

        response = self.client.post(
            "/login",
            data={"username": "test@example.com", "password": password},
        )

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as user_session:
            self.assertEqual(user_session["role"], "enrolled student")
            self.assertEqual(user_session["display_name"], "Test Taker")
            self.assertIn("user_id", user_session)

    def test_registration_uses_a_password_hash_and_assessment_requires_approval(self):
        self.register()
        with closing(sqlite3.connect(self.student_database_path)) as connection, connection:
            password_hash = connection.execute(
                "SELECT password_hash FROM student_users WHERE email = ?",
                ("test@example.com",),
            ).fetchone()[0]
        self.assertNotEqual(password_hash, "student-password")
        self.assertTrue(check_password_hash(password_hash, "student-password"))

        take = self.client.get("/tests/final-english/take")
        self.assertEqual(take.status_code, 302)
        pending = self.client.get("/tests/final-english/register")
        self.assertEqual(pending.status_code, 200)
        self.assertIn(b"Approval required", pending.data)
        submit = self.client.post("/tests/final-english/submit", json={})
        self.assertEqual(submit.status_code, 403)
        self.assertEqual(
            self.client.post(
                "/admin/test-results/users/1/approvals",
                data={"category": "assessment", "approved": "1"},
            ).status_code,
            403,
        )

        approval = self.approve_assessment()
        self.assertEqual(approval.status_code, 302)
        response = self.client.get("/tests/final-english/take")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"question-text", response.data)
        self.assertNotIn(b"correct_answer", response.data)
        self.assertNotIn(b"correct-answer", response.data)

    def test_completed_reports_are_private_linked_to_users_and_retakeable(self):
        self.register()
        self.approve_assessment()
        self.client.get("/tests/final-english/take")
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
        retake = self.client.get("/tests/final-english/take")
        self.assertEqual(retake.status_code, 200)
        lower_score_answers = dict(answers)
        lower_score_answers[questions[0]["id"]] = next(
            answer
            for answer in questions[0]["choices"]
            if answer != questions[0]["correct_answer"]
        )
        self.assertEqual(
            self.client.post(
                "/tests/final-english/submit",
                json=lower_score_answers,
            ).status_code,
            200,
        )
        connection = sqlite3.connect(self.database_path)
        try:
            result = connection.execute(
                """
                SELECT name, email, score, question_count, report_json, user_id
                FROM test_results ORDER BY id
                """
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][:4], ("Test Taker", "test@example.com", 100, 100))
        self.assertEqual(result[1][2], 99)
        self.assertIsNotNone(result[0][5])
        report = json.loads(result[0][4])
        self.assertEqual(len(report), 100)
        self.assertTrue(all(question["is_correct"] for question in report))
        with closing(sqlite3.connect(self.student_database_path)) as connection, connection:
            connection.execute(
                """
                INSERT INTO conjugation_progress
                    (user_id, group_name, completed_series, score)
                VALUES (?, ?, ?, ?)
                """,
                (result[0][5], "Present tense", 3, 42),
            )
            connection.execute(
                """
                CREATE TABLE phantom_pronouns_progress (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    level_key TEXT NOT NULL,
                    best_score INTEGER NOT NULL DEFAULT 0,
                    completed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                INSERT INTO phantom_pronouns_progress
                    (user_id, level_key, best_score, completed)
                VALUES (?, ?, ?, ?)
                """,
                (result[0][5], "2.1", 8, 1),
            )
        with app.app_context():
            connection = connect_word_order_database()
            try:
                connection.execute(
                    """
                    INSERT INTO levels (level_id, level_name_en, level_name_es)
                    VALUES (?, ?, ?)
                    """,
                    (1, "Level One", "Nivel Uno"),
                )
                connection.execute(
                    """
                    INSERT INTO word_order_progress
                        (profile_key, level_id, best_score, completed_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (f"user:{result[0][5]}", 1, 120, "2026-10-02"),
                )
                connection.commit()
            finally:
                connection.close()

        protected = app.test_client().get("/admin/test-results")
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
        self.assertIn(b"99 / 100", admin_results.data)
        self.assertIn(b"Registered students", admin_results.data)
        self.assertIn(b"Revoke assessment access", admin_results.data)
        self.assertIn(b"Verb conjugation", admin_results.data)
        self.assertIn(b"42", admin_results.data)
        self.assertIn(b"Phantom Pronouns", admin_results.data)
        self.assertIn(b"Level One", admin_results.data)
        self.assertIn(b"120", admin_results.data)
        self.assertNotIn(b"student-password", admin_results.data)
        self.assertEqual(admin_results.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
