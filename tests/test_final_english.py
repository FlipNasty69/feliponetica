import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.table import Table

from app import (
    app,
    init_student_database,
    init_test_results_database,
    load_final_english_test,
    load_workbook_tests,
    prepare_database_path,
    student_database_path,
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
        self.workbook_path = os.path.join(self.temp_dir.name, "tests.xlsx")
        self.previous_database_path = app.config.get("TEST_RESULTS_DATABASE_PATH")
        self.previous_student_database_path = app.config.get("STUDENT_DATABASE_PATH")
        self.previous_word_order_database_path = app.config.get("WORD_ORDER_DATABASE")
        self.previous_workbook_path = app.config.get("FINAL_ENGLISH_TEST_WORKBOOK")
        app.config.update(
            TESTING=True,
            TEST_RESULTS_DATABASE_PATH=self.database_path,
            STUDENT_DATABASE_PATH=self.student_database_path,
            WORD_ORDER_DATABASE=self.word_order_database_path,
            FINAL_ENGLISH_TEST_WORKBOOK=self.workbook_path,
        )
        self.create_workbook()
        init_student_database()
        init_test_results_database()
        self.client = app.test_client()

    def create_workbook(self):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "English Test"
        worksheet.append([
            "Question ID", "Type", "Objective", "Category", "Subcategory",
            "Question", "A", "B", "C", "D", "Answer",
        ])
        for index in range(1, 101):
            worksheet.append([
                f"Q{index}", "Multiple Choice", "", "Grammar", "",
                f"Question {index}", "Correct answer", "Wrong answer B",
                "Wrong answer C", "Wrong answer D", "A",
            ])
        workbook.save(self.workbook_path)

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
        if self.previous_workbook_path is None:
            app.config.pop("FINAL_ENGLISH_TEST_WORKBOOK", None)
        else:
            app.config["FINAL_ENGLISH_TEST_WORKBOOK"] = self.previous_workbook_path
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

    def test_student_and_default_results_databases_use_persistent_path(self):
        configured_path = os.path.join(
            self.temp_dir.name,
            "persistent",
            "students.sqlite3",
        )
        with patch.dict(os.environ, {"STUDENT_DATABASE_PATH": configured_path}):
            app.config.pop("STUDENT_DATABASE_PATH", None)
            app.config.pop("TEST_RESULTS_DATABASE_PATH", None)
            self.assertEqual(student_database_path(), configured_path)
            results_path = test_results_database_path()
            self.assertEqual(
                results_path,
                os.path.join(app.instance_path, "test_results.sqlite3"),
            )
            self.assertEqual(prepare_database_path(results_path), results_path)
            self.assertTrue(os.path.isdir(os.path.dirname(results_path)))
        app.config["STUDENT_DATABASE_PATH"] = self.student_database_path
        app.config["TEST_RESULTS_DATABASE_PATH"] = self.database_path

    def test_old_results_are_copied_to_the_new_file_without_deleting_the_source(self):
        with closing(sqlite3.connect(self.student_database_path)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE test_results (
                    id INTEGER PRIMARY KEY,
                    test_name TEXT NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    question_count INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                INSERT INTO test_results (
                    id, test_name, name, email, score, question_count,
                    report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (41, "Old Test", "Saved Student", "", 3, 5, "[]", "2026-01-01"),
            )

        init_test_results_database()
        with closing(sqlite3.connect(self.database_path)) as connection:
            migrated = connection.execute(
                "SELECT id, name, score, user_id FROM test_results"
            ).fetchone()
        with closing(sqlite3.connect(self.student_database_path)) as connection:
            source_count = connection.execute(
                "SELECT COUNT(*) FROM test_results"
            ).fetchone()[0]

        self.assertEqual(migrated, (41, "Saved Student", 3, None))
        self.assertEqual(source_count, 1)

    def test_render_can_start_without_database_or_secret_configuration(self):
        with patch.dict(os.environ, {"RENDER": "true"}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            os.environ.pop("FLASK_SECRET_KEY", None)
            self.assertEqual(test_results_database_path(), self.database_path)

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

    def test_added_worksheets_and_excel_tables_appear_as_tests(self):
        workbook = load_workbook(self.workbook_path)
        table_sheet = workbook.create_sheet("Unit Two")
        table_sheet.append([
            "Question ID", "Category", "Question",
            "Option A", "Option B", "Correct Answer",
        ])
        table_sheet.append(["T1", "Vocabulary", "Table question", "Right", "Wrong", "A"])
        table_sheet.append(["T2", "Vocabulary", "Second table question", "Right", "Wrong", "A"])
        table_sheet.add_table(Table(displayName="UnitTwoQuestions", ref="A1:F3"))

        sheet = workbook.create_sheet("Grammar Review")
        sheet.append([
            "Question ID", "Category", "Question",
            "Option A", "Option B", "Correct Answer",
        ])
        sheet.append(["G1", "Grammar", "Sheet question", "Right", "Wrong", "A"])
        workbook.save(self.workbook_path)

        tests = load_workbook_tests()
        self.assertEqual(
            [test["id"] for test in tests],
            ["final-english", "unit-two-unittwoquestions", "grammar-review"],
        )
        self.assertEqual(tests[1]["name"], "Unit Two — UnitTwoQuestions")
        self.assertEqual(len(tests[1]["questions"]), 2)

        response = self.client.get("/test-center")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Unit Two", response.data)
        self.assertIn(b"Grammar Review", response.data)
        take = self.client.get("/tests/unit-two-unittwoquestions/take")
        self.assertEqual(take.status_code, 200)
        self.assertIn(b"Table question", take.data)

    def test_eleven_column_tables_take_question_text_from_column_f(self):
        workbook = load_workbook(self.workbook_path)
        sheet = workbook.create_sheet("Each Every")
        sheet.append([
            "Question #", "Question Type", "Difficulty Level", "Category",
            "Part of Speech Being Tested", "Question", "Answer A", "Answer B",
            "Answer C", "Correct Answer",
        ])
        sheet.append([
            1, "Multiple Choice", "easy", "determiner", "Grammar",
            "Choose the correct word: ___ student has a book.",
            "Each", "Every", "Each & Every", "C",
        ])
        sheet.add_table(Table(displayName="EachEveryQuestions", ref="A1:J2"))
        workbook.save(self.workbook_path)

        test = next(
            test for test in load_workbook_tests()
            if test["id"] == "each-every-eacheveryquestions"
        )

        self.assertEqual(
            test["questions"][0]["question"],
            "Choose the correct word: ___ student has a book.",
        )
        self.assertEqual(
            test["questions"][0]["choices"],
            {"A": "Each", "B": "Every", "C": "Each & Every"},
        )
        self.assertEqual(test["questions"][0]["correct_answer"], "C")
        take = self.client.get(f"/tests/{test['id']}/take")
        self.assertEqual(take.status_code, 200)
        self.assertIn(
            b"Choose the correct word: ___ student has a book.",
            take.data,
        )

    def test_anyone_can_submit_and_results_are_saved_without_sign_in(self):
        home = self.client.get("/")
        self.assertIn(b"Test Center", home.data)
        take = self.client.get("/tests/final-english/take")
        self.assertEqual(take.status_code, 200)

        answers = {
            question["id"]: question["correct_answer"]
            for question in load_final_english_test()
        }
        response = self.client.post(
            "/tests/final-english/submit",
            json={"answers": answers, "name": "Walk-in Student"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["score"], 100)
        self.assertEqual(response.json["question_count"], 100)
        init_test_results_database()
        with closing(sqlite3.connect(self.database_path)) as connection:
            saved_result = connection.execute(
                "SELECT user_id, name, email FROM test_results"
            ).fetchone()
        self.assertEqual(saved_result, (None, "Walk-in Student", ""))
        self.assertTrue(os.path.isfile(self.database_path))

    def test_test_workbook_and_answer_key_are_not_publicly_downloadable(self):
        response = self.client.get("/static/data/tests.xlsx")

        self.assertEqual(response.status_code, 404)

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

    def test_registration_uses_a_password_hash_but_tests_need_no_approval(self):
        self.register()
        with closing(sqlite3.connect(self.student_database_path)) as connection, connection:
            password_hash = connection.execute(
                "SELECT password_hash FROM student_users WHERE email = ?",
                ("test@example.com",),
            ).fetchone()[0]
        self.assertNotEqual(password_hash, "student-password")
        self.assertTrue(check_password_hash(password_hash, "student-password"))

        take = self.client.get("/tests/final-english/take")
        self.assertEqual(take.status_code, 200)
        pending = self.client.get("/tests/final-english/register")
        self.assertEqual(pending.status_code, 302)
        submit = self.client.post("/tests/final-english/submit", json={})
        self.assertEqual(submit.status_code, 400)
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
        self.assertEqual(response.json["submitted"], True)
        self.assertEqual(response.json["score"], 100)
        self.assertEqual(response.json["question_count"], 100)
        self.assertEqual(response.json["incorrect_questions"], [])
        self.assertNotIn("correct_answer", response.json)
        retake = self.client.get("/tests/final-english/take")
        self.assertEqual(retake.status_code, 200)
        lower_score_answers = dict(answers)
        lower_score_answers[questions[0]["id"]] = next(
            answer
            for answer in questions[0]["choices"]
            if answer != questions[0]["correct_answer"]
        )
        retake_response = self.client.post(
            "/tests/final-english/submit",
            json=lower_score_answers,
        )
        self.assertEqual(retake_response.status_code, 200)
        self.assertEqual(retake_response.json["score"], 99)
        self.assertEqual(
            retake_response.json["incorrect_questions"],
            [{
                "question_number": 1,
                "question": questions[0]["question"],
                "selected_answer": questions[0]["choices"][
                    lower_score_answers[questions[0]["id"]]
                ],
            }],
        )
        self.assertNotIn("correct_answer", retake_response.json)
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
