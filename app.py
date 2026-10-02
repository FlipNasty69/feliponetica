import sqlite3
import os
import smtplib
import json
import re
import secrets
import zipfile

from email.message import EmailMessage
from flask import request, render_template
from flask import Flask, render_template, request, send_from_directory, abort
from flask import session, redirect, url_for
from features.feliponetica import feliponetica_bp
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from werkzeug.security import check_password_hash

app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_COOKIE_SECURE", "0") == "1",
)
STUDENT_DATABASE_PATH = os.path.join(app.root_path, "student_users.db")
TEST_RESULTS_ADMIN_PASSWORD_HASH = os.environ.get(
    "TEST_RESULTS_ADMIN_PASSWORD_HASH",
    "pbkdf2:sha256:600000$pgzAbeZ0AQmCtlwz$249a511824fc4651e9f4a0be139f920088c6ab99db794a1ce50a8c45391107a8",
)
USERS = {
    "felipe": {
        "password": "felipe",
        "role": "admin",
    }
}

# ============================================================
# GAME BLUEPRINTS
# ============================================================
# Add future game blueprints here and then register them below.
# Example:
# from games.vocab_game import vocab_bp
# GAME_BLUEPRINTS = [vocab_bp]
from games.vocab_game import vocab_bp
from games.phantom_pronouns import phantom_pronouns_bp
from word_order import word_order_bp
from word_order.cli import register_cli
GAME_BLUEPRINTS = [vocab_bp, phantom_pronouns_bp, word_order_bp]

def register_game_blueprints():
    for blueprint in GAME_BLUEPRINTS:
        app.register_blueprint(blueprint)


register_game_blueprints()
app.register_blueprint(feliponetica_bp)
register_cli(app)


def init_student_database():
    with sqlite3.connect(STUDENT_DATABASE_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS student_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                username TEXT UNIQUE,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'student'
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS conjugation_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                group_name TEXT NOT NULL,
                completed_series INTEGER NOT NULL DEFAULT 0,
                current_verb INTEGER NOT NULL DEFAULT 0,
                score INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, group_name),
                FOREIGN KEY(user_id) REFERENCES student_users(id)
            )
        """)
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(conjugation_progress)").fetchall()
        }
        if "current_verb" not in columns:
            connection.execute(
                "ALTER TABLE conjugation_progress ADD COLUMN current_verb INTEGER NOT NULL DEFAULT 0"
            )
        student_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(student_users)").fetchall()
        }
        if "username" not in student_columns:
            connection.execute("ALTER TABLE student_users ADD COLUMN username TEXT")
        if "role" not in student_columns:
            connection.execute(
                "ALTER TABLE student_users ADD COLUMN role TEXT NOT NULL DEFAULT 'student'"
            )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS student_users_username_idx ON student_users(username)"
        )


init_student_database()


def test_results_database_path():
    return app.config.get("TEST_RESULTS_DATABASE_PATH", STUDENT_DATABASE_PATH)


def init_test_results_database():
    connection = sqlite3.connect(test_results_database_path())
    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_name TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                score INTEGER NOT NULL,
                question_count INTEGER NOT NULL,
                report_json TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()
    finally:
        connection.close()


init_test_results_database()


def load_final_english_test():
    workbook_path = app.config.get(
        "FINAL_ENGLISH_TEST_WORKBOOK",
        os.path.join(app.root_path, "static", "data", "tests.xlsx"),
    )
    try:
        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
        try:
            if "English Test" not in workbook.sheetnames:
                raise ValueError("The workbook must contain an 'English Test' sheet.")
            worksheet = workbook["English Test"]
            questions = []
            question_ids = set()
            for row in worksheet.iter_rows(min_row=2, values_only=True):
                if not row or len(row) < 11 or not row[5]:
                    continue
                question_type = str(row[1] or "").strip()
                if question_type != "Multiple Choice":
                    raise ValueError(
                        f"Unsupported question type in question {row[0]}: {question_type}"
                    )
                choices = {
                    label: str(row[column]).strip()
                    for label, column in zip("ABCD", range(6, 10))
                    if row[column] is not None and str(row[column]).strip()
                }
                correct_answer = str(row[10] or "").strip().upper()
                question_id = str(row[0] or len(questions) + 1).strip()
                if (
                    question_id in question_ids
                    or len(choices) < 2
                    or correct_answer not in choices
                ):
                    raise ValueError(
                        f"Question {question_id} has a duplicate ID, incomplete choices, "
                        "or an invalid answer."
                    )
                question_ids.add(question_id)
                questions.append({
                    "id": question_id,
                    "category": str(row[3] or "").strip(),
                    "question": str(row[5]).strip(),
                    "choices": choices,
                    "correct_answer": correct_answer,
                })
            if not questions:
                raise ValueError("The workbook does not contain any test questions.")
            return questions
        finally:
            workbook.close()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, InvalidFileException) as error:
        app.logger.exception("Could not load the Final English Test workbook.")
        raise RuntimeError("The Final English Test is temporarily unavailable.") from error


def valid_test_email(email):
    if not email or len(email) > 254 or email.count("@") != 1:
        return False
    local, domain = email.rsplit("@", 1)
    if (
        not local
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
    ):
        return False
    labels = domain.split(".")
    return (
        len(labels) >= 2
        and all(
            len(label) <= 63
            and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
            for label in labels
        )
    )


def is_logged_in():
    return "username" in session and "role" in session


def require_login():
    if not is_logged_in():
        return redirect(url_for("login"))
    return None

# ============================================================
# JSON DATA
# ============================================================

def load_data(file_path):

    import os

    full_path = os.path.join(
        app.root_path,
        file_path
    )

    try:

        with open(
            full_path,
            'r',
            encoding='utf-8'
        ) as f:

            return json.load(f)

    except FileNotFoundError:

        return {}

# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    message = ""
    next_url = request.args.get("next", "")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next", next_url)

        user = USERS.get(username)
        registered_user = None
        if not user:
            with sqlite3.connect(STUDENT_DATABASE_PATH) as connection:
                connection.row_factory = sqlite3.Row
                registered_user = connection.execute(
                    "SELECT * FROM student_users WHERE email = ? OR username = ?",
                    (username.strip().lower(), username.strip().lower())
                ).fetchone()

        configured_password_matches = user and user["password"] == password
        registered_password_matches = (
            registered_user and registered_user["password_hash"] == password
        )
        if configured_password_matches or registered_password_matches:
            session["username"] = username
            session["role"] = user["role"] if user else registered_user["role"]
            if registered_user:
                session["user_id"] = registered_user["id"]
                session["display_name"] = f"{registered_user['name']} {registered_user['last_name']}"
            else:
                session.pop("user_id", None)
                session["display_name"] = username
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("home")
            return redirect(next_url)
        else:
            message = "Invalid email or password."

    return render_template("login.html", message=message, next_url=next_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    message = ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not all([name, last_name, email, password]):
            message = "All fields are required."
        else:
            with sqlite3.connect(STUDENT_DATABASE_PATH) as connection:
                try:
                    connection.execute(
                        "INSERT INTO student_users (name, last_name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                        (name, last_name, email, password, "student")
                    )
                    connection.commit()
                except sqlite3.IntegrityError:
                    message = "That email is already registered."
                else:
                    session["username"] = email
                    session["role"] = "enrolled student"
                    session["user_id"] = connection.execute(
                        "SELECT id FROM student_users WHERE email = ?", (email,)
                    ).fetchone()[0]
                    session["display_name"] = f"{name} {last_name}"
                    return redirect(url_for("verb_conjugation_game"))
    return render_template("register.html", message=message)


@app.route("/verb-conjugation-game")
@app.route("/verb_conjugation_game")
def verb_conjugation_game():
    guest_mode = request.args.get("guest") == "1"
    saved_user = bool(session.get("user_id")) and not guest_mode
    return render_template(
        "verb_conjugation_game.html",
        display_name=session.get("display_name", "Guest") if saved_user else "Guest",
        saved_user=saved_user,
        guest_mode=guest_mode,
        admin_mode=session.get("role") == "admin"
    )


@app.route("/api/conjugation-progress", methods=["GET", "POST"])
def conjugation_progress():
    user_id = session.get("user_id")
    if not user_id:
        return {"saved": False, "progress": {}}

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        group_name = str(payload.get("group_name", "")).strip()
        completed_series = max(0, int(payload.get("completed_series", 0)))
        current_verb = max(0, int(payload.get("current_verb", 0)))
        score = max(0, int(payload.get("score", 0)))
        if not group_name:
            return {"error": "group_name is required"}, 400
        with sqlite3.connect(STUDENT_DATABASE_PATH) as connection:
            connection.execute("""
                INSERT INTO conjugation_progress (user_id, group_name, completed_series, current_verb, score)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, group_name) DO UPDATE SET
                    completed_series = excluded.completed_series,
                    current_verb = excluded.current_verb,
                    score = excluded.score
            """, (user_id, group_name, completed_series, current_verb, score))
            connection.commit()
        return {"saved": True}

    with sqlite3.connect(STUDENT_DATABASE_PATH) as connection:
        rows = connection.execute("""
            SELECT group_name, completed_series, current_verb, score
            FROM conjugation_progress
            WHERE user_id = ?
        """, (user_id,)).fetchall()
    return {
        "saved": True,
        "progress": {
            row[0]: {"completedSeries": row[1], "currentVerb": row[2], "score": row[3]}
            for row in rows
        }
    }


@app.route("/api/conjugation-data")
def conjugation_data():
    workbook_path = os.path.join(
        app.root_path, "static", "data", "verbs_master_table.xlsx"
    )
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        worksheet = workbook["Verbs"]
        header_row = next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
        headers = [header for header in header_row if header]
        required_headers = {"parent_category", "series_id", "series_title"}
        if not required_headers.issubset(headers):
            return {"error": "The verbs master table has an invalid header row."}, 500

        groups = {}
        series_by_key = {}
        metadata_headers = {"parent_category", "series_id", "series_title"}
        for row in worksheet.iter_rows(min_row=2, values_only=True):
            if not row or all(value is None for value in row):
                continue
            values = {
                header: row[index] if index < len(row) else None
                for index, header in enumerate(header_row)
                if header
            }
            category = values.get("parent_category")
            if not category:
                continue

            group = groups.setdefault(category, {"series": []})
            series_key = (category, values.get("series_id"))
            series = series_by_key.get(series_key)
            if series is None:
                series = {
                    "id": values.get("series_id") or "",
                    "title": values.get("series_title") or "",
                    "verbs": [],
                }
                series_by_key[series_key] = series
                group["series"].append(series)

            series["verbs"].append({
                header: "" if value is None else value
                for header, value in values.items()
                if header not in metadata_headers
            })
        return app.response_class(
            json.dumps(groups, ensure_ascii=False), mimetype="application/json"
        )
    finally:
        workbook.close()



# ============================================================
# SUPPORT DATABASE
# ============================================================

def init_support_database():

    conn = sqlite3.connect("support_messages.db")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


init_support_database()


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    return render_template("index.html")



# ============================================================
# VOCABULARY SETS
# ============================================================

VOCABULARY_SETS = {

    "basic-adjectives": {
        "title": "Basic Adjectives",
        "description": "Common adjectives for describing people, things, and situations.",
        "words": [
            "good = bueno",
            "bad = malo",
            "easy = fácil",
            "difficult = difícil",
            "big = grande",
            "small = pequeño",
            "tall = alto",
            "short = corto",
            "high = alto",
            "low = bajo",
            "hot = caliente",
            "cold = frío",
            "fast = rápido",
            "slow = lento",
            "happy = feliz",
            "sad = triste",
        ]
    },

    "subject-object-clauses": {
        "title": "Sub and Obj Clause Vocab",
        "description": "Words used to begin subject and object clauses.",
        "words": [
            "who = quien",
            "whose = de quien sea",
            "what = que",
            "when = cuando",
            "where = donde",
            "why = por qué",
            "how = como",
            "that = que", 
        ]
    },

  "subject-object-clauses else": {
        "title": "Sub and Obj Clause Vocab (else)",
        "description": "Words used to begin subject and object clauses with (else).",
        "words": [
            "who else = quien mas",
            "what else = que mas",
            "when else = cuando mas",
            "where else = donde mas",
            "why else = por qué mas / por que otra razón",
            "how else = como mas / de que otra manera"
        ]
    },

    "subject-object-clauses ever": {
        "title": "Sub and Obj Clause Vocab (ever)",
        "description": "Words used to begin subject and object clauses with (ever).",
        "words": [
            "whoever = quien sea",
            "whatever = que sea",
            "whenever = cuando sea",
            "wherever = donde sea",
            "whyever = por la razon qué sea",
            "however = como sea"
        ]
    },

    "everyday-vocabulary": {
        "title": "Everyday Vocabulary",
        "description": "Useful words that appear constantly in everyday English.",
        "words": [
            "thing = cosa",
            "way = camino, manera, forma",
            "place = lugar",
            "time = tiempo",
            "people = gente",
            "stuff = cosas"
        ]
    },

    "everyday-english": {
        "title": "Everyday English",
        "description": "Useful English vocabulary for everyday situations.",
        "words": [
            "lucky = afortunado",
            "unusual = no común",
            "silly = tonto",
            "strong = fuerte",
            "easy = fácil",
            "difficult = difícil",
            "busy = ocupado",
            "quiet = tranquilo",
            "careful = cuidadoso",
            "important = importante"
        ]
    },

    "essential-verbs": {
        "title": "Essential Verbs",
        "description": "High-frequency verbs used to build everyday English sentences.",
        "words": [
            "be = ser / estar",
            "have = tener",
            "do = hacer",
            "go = ir",
            "make = hacer / crear",
            "take = tomar / llevar",
            "come = venir",
            "put = poner",
            "leave = irse / dejar",
            "run = correr",
            "say = decir",
            "tell = contar / decir",
            "call = llamar"
        ]
    },

    "work": {
        "title": "Work Vocabulary",
        "description": "Practical vocabulary for talking about work, jobs, and daily responsibilities.",
        "words": [
            "job = trabajo",
            "shift = turno",
            "worker = trabajador",
            "manager = gerente",
            "meeting = reunión",
            "schedule = horario"
        ]
    },

    "colors": {
        "title": "Colors",
        "description": "Common colors for describing people, objects, clothes, and places.",
        "words": [
            "red = rojo",
            "blue = azul",
            "green = verde",
            "yellow = amarillo",
            "orange = naranja",
            "purple = morado",
            "pink = rosa",
            "brown = café",
            "black = negro",
            "white = blanco",
            "gray = gris",
            "gold = dorado",
            "silver = plateado"
        ]
    },

    "numbers": {
        "title": "Numbers",
        "description": "Numbers from 1 to 10",
        "words": [
            "1 = one wan",
            "2 = two tu",
            "3 = three thri",
            "4 = four for",
            "5 = five faiv",
            "6 = six siks",
            "7 = seven",
            "8 = eight eit",
            "9 = nine nain",
            "10 = ten ten"
        ]
    },

}


# ============================================================
# VOCABULARY PAGE
# ============================================================

@app.route('/vocab_drill')
def vocab():

    access_error = require_login()
    if access_error:
        return access_error

    return render_template(
        'vocab_drill.html',
        vocabulary_sets=VOCABULARY_SETS
    )


# ============================================================
# LESSONS
# ============================================================

@app.route('/lessons')
def lessons():

    access_error = require_login()
    if access_error:
        return access_error

    import os

    lessons_folder = os.path.join(
        app.root_path,
        'lessons'
    )

    lesson_files = []

    if os.path.exists(lessons_folder):

        for filename in os.listdir(lessons_folder):

            if filename.lower().endswith('.pdf'):

                lesson_files.append(filename)

    lesson_files.sort()

    return render_template(
        'lessons.html',
        lessons=lesson_files
    )


# ============================================================
# OPEN LESSON PDF
# ============================================================

@app.route('/lesson-pdf/<path:filename>')
def lesson_pdf(filename):

    import os

    lessons_folder = os.path.join(
        app.root_path,
        'lessons'
    )

    return send_from_directory(
        lessons_folder,
        filename
    )


# ============================================================
# COURSE
# ============================================================

@app.route('/course')
def course():

    access_error = require_login()
    if access_error:
        return access_error

    return render_template('course.html')


@app.route("/test-center")
def test_center():
    return render_template("test_center.html")


@app.route("/tests/final-english/register", methods=["GET", "POST"])
def final_english_register():
    message = ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        if not name or len(name) > 120:
            message = "Enter your name (up to 120 characters)."
        elif not valid_test_email(email):
            message = "Enter a valid email address."
        else:
            session["final_english_tester"] = {"name": name, "email": email}
            return redirect(url_for("final_english_take"))
    return render_template("test_registration.html", message=message)


@app.route("/tests/final-english/take")
def final_english_take():
    tester = session.get("final_english_tester")
    if not tester:
        return redirect(url_for("final_english_register"))
    try:
        questions = load_final_english_test()
    except RuntimeError:
        abort(503, description="The Final English Test is temporarily unavailable.")
    public_questions = [
        {
            "id": question["id"],
            "category": question["category"],
            "question": question["question"],
            "choices": question["choices"],
        }
        for question in questions
    ]
    return render_template(
        "test_take.html",
        questions=public_questions,
        test_name="Final English Test",
    )


@app.route("/tests/final-english/submit", methods=["POST"])
def final_english_submit():
    tester = session.get("final_english_tester")
    if not tester:
        return {"error": "Register before submitting the test."}, 401
    if not request.is_json:
        return {"error": "A JSON answer report is required."}, 400
    answers = request.get_json(silent=True)
    if not isinstance(answers, dict):
        return {"error": "The submitted answers are invalid."}, 400
    try:
        questions = load_final_english_test()
    except RuntimeError:
        abort(503, description="The Final English Test is temporarily unavailable.")

    expected_ids = {question["id"] for question in questions}
    if set(answers) != expected_ids or any(
        not isinstance(answer, str)
        or answer not in question["choices"]
        for question in questions
        for answer in [answers.get(question["id"])]
    ):
        return {"error": "Answer every question before submitting."}, 400

    report = []
    score = 0
    for question in questions:
        selected_answer = answers[question["id"]]
        is_correct = selected_answer == question["correct_answer"]
        score += int(is_correct)
        report.append({
            "question_id": question["id"],
            "category": question["category"],
            "question": question["question"],
            "choices": question["choices"],
            "selected_answer": selected_answer,
            "correct_answer": question["correct_answer"],
            "is_correct": is_correct,
        })

    connection = sqlite3.connect(test_results_database_path())
    try:
        connection.execute(
            """
            INSERT INTO test_results (
                test_name, name, email, score, question_count, report_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "Final English Test",
                tester["name"],
                tester["email"],
                score,
                len(questions),
                json.dumps(report, ensure_ascii=False),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    session.pop("final_english_tester", None)
    return {"submitted": True}


@app.route("/admin/test-results", methods=["GET", "POST"])
def admin_test_results():
    if request.method == "POST":
        password = request.form.get("password", "")
        if check_password_hash(TEST_RESULTS_ADMIN_PASSWORD_HASH, password):
            session["test_results_admin_authenticated"] = True
            return redirect(url_for("admin_test_results"))
        return render_template(
            "test_results_admin.html",
            authenticated=False,
            message="Incorrect password.",
        ), 401

    if not session.get("test_results_admin_authenticated"):
        return render_template(
            "test_results_admin.html",
            authenticated=False,
            message="",
        )

    connection = sqlite3.connect(test_results_database_path())
    try:
        connection.row_factory = sqlite3.Row
        results = connection.execute(
            "SELECT * FROM test_results ORDER BY created_at DESC, id DESC"
        ).fetchall()
    finally:
        connection.close()
    response = app.make_response(render_template(
        "test_results_admin.html",
        authenticated=True,
        results=[
            {**dict(result), "report": json.loads(result["report_json"])}
            for result in results
        ],
    ))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/admin/test-results/logout", methods=["POST"])
def admin_test_results_logout():
    session.pop("test_results_admin_authenticated", None)
    return redirect(url_for("admin_test_results"))


# ============================================================
# MODULES
# ============================================================

@app.route('/module/<module_id>')
def interactive_module(module_id):

    access_error = require_login()
    if access_error:
        return access_error

    # --------------------------------------------------------
    # LOAD JSON DATA
    # --------------------------------------------------------

    videos_data = load_data('static/data/videos.json')
    quizzes_data = load_data('static/data/quizzes.json')


    # --------------------------------------------------------
    # FIND THE REQUESTED MODULE
    # --------------------------------------------------------

    video_module = videos_data.get(module_id)
    quiz_module = quizzes_data.get(module_id)

    if not video_module and not quiz_module:
        return f"URL module_id = [{module_id}]<br>JSON keys = {list(videos_data.keys())}"

    content_module = video_module or quiz_module


    # --------------------------------------------------------
    # CREATE THE MODULE
    # --------------------------------------------------------

    module = {

        "title": content_module.get(
            "title",
            module_id
        ),

        "description": content_module.get(
            "description",
            ""
        ),

        "series": []

    }


    # --------------------------------------------------------
    # INDEX THE QUIZ SERIES
    # --------------------------------------------------------

    quiz_series = {}

    if quiz_module:

        for series in quiz_module.get(
            "series",
            []
        ):

            quiz_series[
                series.get("id")
            ] = series


    # --------------------------------------------------------
    # COMBINE VIDEO + QUIZ SERIES
    # --------------------------------------------------------

    video_series = {
        series.get("id"): series
        for series in (video_module or {}).get("series", [])
    }

    all_series_ids = list(
        dict.fromkeys(
            list(video_series.keys()) +
            list(quiz_series.keys())
        )
    )

    for series_id in all_series_ids:

        video_series_data = video_series.get(series_id, {})
        quiz_series_data = quiz_series.get(series_id, {})


        combined_series = {

            "id": series_id,

            "title": video_series_data.get(
                "title",
                quiz_series_data.get("title", f"Series {series_id}")
            ),

            "description": video_series_data.get(
                "description",
                quiz_series_data.get("description", "")
            ),

            "videos": video_series_data.get(
                "videos",
                []
            ),

            "quiz": quiz_series_data.get(
                "questions",
                []
            ),

            "audio": video_series_data.get(
                "audio",
                []
            ),

            "images": video_series_data.get(
                "images",
                []
            )

        }


        module["series"].append(
            combined_series
        )


    # --------------------------------------------------------
    # SEND COMPLETE MODULE TO HTML
    # --------------------------------------------------------

    return render_template(
        'module.html',
        module=module
    )
# ============================================================
# GAMES
# ============================================================

@app.route('/games')
def games_dashboard():

    return render_template('games.html')

    if __name__ == "__main__":
        app.run(host='0.0.0.0.', por=5000, debug=Ture)

# ============================================================
# ABOUT
# ============================================================

@app.route('/about')
def about():
    return render_template('about.html')


# ============================================================
# LIVE CLASSES
# ============================================================

@app.route('/live_classes')
def live_classes():
    return render_template('live_classes.html')


# ============================================================
# CONTACT
# ============================================================

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route("/tech-support", methods=["GET", "POST"])
def tech_support():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        subject = request.form["subject"]
        message = request.form["message"]

        conn = sqlite3.connect("support_messages.db")

        conn.execute("""
            INSERT INTO support_messages
            (name, email, subject, message)
            VALUES (?, ?, ?, ?)
        """, (name, email, subject, message))

        conn.commit()
        conn.close()

        return render_template(
            "tech_support.html",
            success=True
        )

    return render_template("tech_support.html")

@app.route("/support_messages")
def support_messages():

    access_error = require_login()
    if access_error:
        return access_error

    if session["role"] == "enrolled student":
        return "Access denied"

    conn = sqlite3.connect("support_messages.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, email, subject, message, created_at
        FROM support_messages
        ORDER BY created_at DESC
    """)

    messages = cursor.fetchall()
    conn.close()

    return render_template(
        "support_messages.html",
        messages=messages
    )

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
