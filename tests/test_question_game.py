import os
import tempfile
import unittest
from openpyxl import Workbook

from app import app
from games import question_game


class QuestionGameTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_workbook_loads_all_level_one_sheets_from_table_rows(self):
        with app.app_context():
            data = question_game.get_game_data()

        exercises = data["levels"]
        self.assertEqual(
            set(exercises),
            {
                "level1-exercise",
                "level1-do",
                "level1-present-be",
                "level1-past-be",
                "level1-be",
            },
        )
        level_one = exercises["level1-exercise"]["questions"]
        self.assertEqual(len(level_one), 48)
        work_question = next(
            question for question in level_one
            if [word.casefold() for word in question["answer"]]
            == ["do", "you", "work?"]
        )
        self.assertEqual(work_question["prompt"], "¿Trabajas?")
        self.assertEqual(work_question["slot_labels"], ["bully", "subject", "verbo bulliado"])

        do_questions = exercises["level1-do"]["questions"]
        self.assertEqual(len(do_questions), 45)
        self.assertFalse(any(
            "NOTE:" in word
            for question in do_questions
            for word in question["answer"]
        ))

    def test_rows_with_optional_adverbs_create_additional_slots(self):
        with app.app_context():
            questions = question_game.get_game_data()["levels"][
                "level1-present-be"
            ]["questions"]

        adverb_question = next(
            question for question in questions if len(question["answer"]) == 4
        )
        self.assertEqual(adverb_question["answer"], ["Am", "I", "eating", "right?"])
        self.assertEqual(
            adverb_question["slot_labels"],
            ["Word 1", "Word 2", "Word 3", "adverb"],
        )

    def test_game_page_and_game_area_links(self):
        page = self.client.get("/question-game/game")
        dashboard = self.client.get("/games")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Question Builder", page.data)
        self.assertIn(b"Choose an exercise", page.data)
        self.assertIn(b"exercise-options", page.data)
        self.assertIn(b"Question Builder", dashboard.data)
        self.assertIn(b'href="/question-game/game"', dashboard.data)

        with self.client.session_transaction() as user_session:
            user_session["username"] = "student@example.com"
            user_session["role"] = "enrolled student"
        course = self.client.get("/course")
        self.assertEqual(course.status_code, 200)
        self.assertIn(b"Play Question Builder", course.data)
        self.assertIn(b'href="/question-game/game"', course.data)

    def test_exercise_list_includes_every_level_one_sheet(self):
        response = self.client.get("/question-game/api/exercises")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {exercise["id"] for exercise in payload["exercises"]},
            {
                "level1-exercise",
                "level1-do",
                "level1-present-be",
                "level1-past-be",
                "level1-be",
            },
        )

    def test_round_keeps_answers_secret_and_generates_slot_labels(self):
        response = self.client.get(
            "/question-game/api/round?level=level1-present-be"
        )
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["total"], 40)
        questions = [
            question
            for batch in payload["batches"]
            for question in batch["questions"]
        ]
        self.assertEqual(len(questions), 40)
        adverb_question = next(
            question for question in questions if len(question["slot_labels"]) == 4
        )
        self.assertEqual(adverb_question["slot_labels"], [
            "Word 1", "Word 2", "Word 3", "adverb",
        ])
        self.assertTrue(all(
            "answer" not in question
            for batch in payload["batches"]
            for question in batch["questions"]
        ))
        for batch in payload["batches"]:
            words = [tile["word"].casefold() for tile in batch["word_bank"]]
            self.assertEqual(len(words), len(set(words)))

    def test_answer_check_accepts_any_number_of_row_slots(self):
        with app.app_context():
            exercise = question_game.get_game_data()["levels"]["level1-present-be"]
            question = next(item for item in exercise["questions"] if len(item["answer"]) == 4)

        response = self.client.post(
            "/question-game/api/check",
            json={
                "level": "level1-present-be",
                "answers": [{"id": question["id"], "words": question["answer"]}],
            },
        )
        invalid_response = self.client.post(
            "/question-game/api/check",
            json={
                "level": "level1-present-be",
                "answers": [{
                    "id": question["id"],
                    "words": question["answer"][:3],
                }],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["results"][0]["correct"])
        self.assertEqual(invalid_response.status_code, 400)

    def test_new_sheet_and_arbitrary_slot_count_are_discovered_automatically(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Level 1 Future"
        sheet.append([
            "Spanish prompt", "Auxiliary", "Subject", "Verb",
            "Adverb", "Time", "Place",
        ])
        sheet.append([
            "¿Puedes viajar?", "Can", "you", "travel", None, "tomorrow", "alone",
        ])

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "question_game.xlsx")
            workbook.save(path)
            previous_cache = question_game._game_data_cache
            previous_path = app.config.get("QUESTION_GAME_WORKBOOK")
            question_game._game_data_cache = None
            app.config["QUESTION_GAME_WORKBOOK"] = path
            try:
                exercises_response = self.client.get("/question-game/api/exercises")
                self.assertEqual(
                    [exercise["id"] for exercise in exercises_response.get_json()["exercises"]],
                    ["level1-future"],
                )
                round_response = self.client.get(
                    "/question-game/api/round?level=level1-future"
                )
                payload = round_response.get_json()
                question = payload["batches"][0]["questions"][0]
                self.assertEqual(question["slot_labels"], [
                    "Auxiliary", "Subject", "Verb", "Time", "Place",
                ])
                self.assertNotIn("answer", question)
                answer_check = self.client.post(
                    "/question-game/api/check",
                    json={
                        "level": "level1-future",
                        "answers": [{
                            "id": question["id"],
                            "words": ["Can", "you", "travel", "tomorrow", "alone"],
                        }],
                    },
                )
                self.assertEqual(answer_check.status_code, 200)
                self.assertTrue(answer_check.get_json()["results"][0]["correct"])
            finally:
                if previous_path is None:
                    app.config.pop("QUESTION_GAME_WORKBOOK", None)
                else:
                    app.config["QUESTION_GAME_WORKBOOK"] = previous_path
                question_game._game_data_cache = previous_cache
                workbook.close()

    def test_round_and_answer_check_reject_invalid_inputs(self):
        invalid_level = self.client.get("/question-game/api/round?level=unknown")
        invalid_answer = self.client.post(
            "/question-game/api/check",
            json={"level": "level1-exercise", "answers": [{"id": "missing", "words": ["do"]}]},
        )
        self.assertEqual(invalid_level.status_code, 400)
        self.assertEqual(invalid_answer.status_code, 400)


if __name__ == "__main__":
    unittest.main()
