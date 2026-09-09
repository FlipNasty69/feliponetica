import sqlite3
import os
import smtplib
import json
import nltk
import re

from email.message import EmailMessage
from flask import request, render_template
from flask import Flask, render_template, request, send_from_directory, abort
from g2p_en import G2p
from flask import session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change this
STUDENT_DATABASE_PATH = os.path.join(app.root_path, "student_users.db")

USERS = {
    "felipe": {"password": "03162025", "role": "admin"},
    "karina": {"password": "03162025", "role": "admin"},
    "student": {"password": "i sent the song", "role": "student"},
    "L-English": {"password": "Flip's Class", "role": "enrolled student"},
    "Punto Ingles": {"password": "Flip's Class", "role": "enrolled student"},
    "Jesica": {"password": "#1", "role": "enrolled student"}
}


def init_student_database():
    with sqlite3.connect(STUDENT_DATABASE_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS student_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
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


init_student_database()


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
                    "SELECT * FROM student_users WHERE email = ?",
                    (username.strip().lower(),)
                ).fetchone()

        registered_password_matches = registered_user and check_password_hash(
            registered_user["password_hash"], password
        )
        if (user and user["password"] == password) or registered_password_matches:
            session["username"] = username
            session["role"] = user["role"] if user else "student"
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
                        "INSERT INTO student_users (name, last_name, email, password_hash) VALUES (?, ?, ?, ?)",
                        (name, last_name, email, generate_password_hash(password))
                    )
                    connection.commit()
                except sqlite3.IntegrityError:
                    message = "That email is already registered."
                else:
                    session["username"] = email
                    session["role"] = "student"
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
        guest_mode=guest_mode
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


# ============================================================
# NLTK DATA
# ============================================================

NLTK_DATA_PATH = "/opt/render/nltk_data"

nltk.data.path.insert(0, NLTK_DATA_PATH)

nltk.download(
    "averaged_perceptron_tagger_eng",
    download_dir=NLTK_DATA_PATH
)

nltk.download(
    "cmudict",
    download_dir=NLTK_DATA_PATH
)

g2p = G2p()

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
# FELIPONETICA
# ============================================================

CMU_TO_FELIPONETICA = {

    # Vowels
    "AA": "a˂",
    "AE": "aʰ",
    "AH": "uʰ",
    "AO": "a˂",
    "AW": "au",
    "AY": "ai",
    "EH": "e",
    "ER": "er",
    "EY": "ei",
    "IH": "iʰ",
    "IY": "i",
    "OW": "ou",
    "OY": "oi",
    "UH": "uᶠ",
    "UW": "u",

    # Stops
    "P": "p",
    "B": "b",
    "T": "t",
    "D": "d",
    "K": "k",
    "G": "g",

    # Fricatives
    "F": "f",
    "V": "v",
    "TH": "thˢ",
    "DH": "thᶻ",
    "S": "s",
    "Z": "z",
    "SH": "sh",
    "ZH": "shᶻ",
    "HH": "j",

    # Affricates
    "CH": "ch",
    "JH": "shᶻ",

    # Nasals
    "M": "m",
    "N": "n",
    "NG": "ng",

    # Liquids
    "L": "l",
    "R": "r",

    # Glides
    "W": "w",
    "Y": "ll",
}


def convert_to_feliponetica(text):

    phonemes = g2p(text)

    # =====================================================
    # WORD-SPECIFIC PRONUNCIATION CORRECTIONS
    # =====================================================

    # "with" uses the voiceless TH sound in Feliponetica
    # with → W IH TH
    for i, phone in enumerate(phonemes):

        clean_phone = re.sub(r"\d", "", phone)

        if clean_phone == "DH":

            previous_1 = ""
            previous_2 = ""

            if i > 0:
                previous_1 = re.sub(r"\d", "", phonemes[i - 1])

            if i > 1:
                previous_2 = re.sub(r"\d", "", phonemes[i - 2])

            if previous_2 == "W" and previous_1 == "IH":
                phonemes[i] = "TH"

    converted = []

    i = 0

    while i < len(phonemes):

        phone = phonemes[i]

        # =================================================
        # KEEP SPACES
        # =================================================

        if phone == " ":
            converted.append(" ")
            i += 1
            continue

        # =================================================
        # KEEP PUNCTUATION
        # =================================================

        if not re.match(r"^[A-Z]+[0-2]?$", phone):
            converted.append(phone)
            i += 1
            continue

        # Remove stress number
        phone = re.sub(r"\d", "", phone)

        # Get next phoneme
        next_phone = ""

        if i + 1 < len(phonemes):
            next_phone = re.sub(
                r"\d", "",
                phonemes[i + 1]
            )

        # Get phoneme after next
        after_next_phone = ""

        if i + 2 < len(phonemes):
            after_next_phone = re.sub(
                r"\d", "",
                phonemes[i + 2]
            )

                # =================================================
        # Y + UW + AH + L
        # =================================================

        # fuel → fiuol

        if (
            phone == "Y"
            and next_phone == "UW"
            and after_next_phone == "AH"
        ):

            if i + 3 < len(phonemes):
                after_ah_phone = re.sub(
                    r"\d", "",
                    phonemes[i + 3]
                )

                if after_ah_phone == "L":
                    converted.append("iuol")
                    i += 4
                    continue


        # =================================================
        # Y + UW + L
        # =================================================
        #
        # mule → miuol
        # fuel → fiuol
        #
        # Y UW L → iuol

        if (
            phone == "Y"
            and next_phone == "UW"
            and after_next_phone == "L"
        ):

            converted.append("iuol")

            i += 3
            continue


        # =================================================
        # Y + UW
        # =================================================
        #
        # few → fiu
        # future → fiuchr
        # fusion → fiu...

        if phone == "Y" and next_phone == "UW":

            converted.append("iu")

            i += 2
            
            continue

        # =================================================
        # AO + R
        # =================================================
        #
        # north
        # core
        # bore
        # store
        # chore
        # lore
        # more
        #
        # AO R → o r

        if phone == "AO" and next_phone == "R":

            converted.append("or")

            i += 2
            continue

        # =================================================
        # NG + K
        # =================================================
        #
        # think
        # thank
        # drink
        # bank
        #
        # NG K → n k

        if phone == "NG" and next_phone == "K":

            converted.append("nk")

            i += 2
            continue

        # =================================================
        # FINAL L RULE
        # =================================================
        #
        # UW + L → uol
        # IY + L → iol
        # EY + L → eiol
        # AY + L → aiol
        # OY + L → oiol
        #
        # Examples:
        #
        # full   → fuol
        # feel   → fiol
        # school → skuol
        # male   → meiol
        # tail   → teiol
        # oil    → oiol
        #
        # IH + L is NOT changed.
        #
        # fill → fiʰl
        # hill → hiʰl

        if (
            phone in ["UW", "IY", "EY", "AY", "OY"]
            and next_phone == "L"
        ):

            vowel = CMU_TO_FELIPONETICA.get(
                phone,
                phone
            )

            converted.append(vowel + "ol")

            i += 2
            continue

        # =================================================
        # NORMAL CMU → FELIPONETICA
        # =================================================

        converted.append(
            CMU_TO_FELIPONETICA.get(
                phone,
                phone
            )
        )

        i += 1

    return "".join(converted)

# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    return render_template("index.html")



# ============================================================
# FELIPONETICA
# ============================================================

@app.route('/feliponetica', methods=['GET', 'POST'])
def feliponetica():

    access_error = require_login()
    if access_error:
        return access_error

    result = None
    user_input = ""

    if request.method == 'POST':

        user_input = request.form.get(
            'transcript_text',
            ''
        ).strip()

        if user_input:
            result = convert_to_feliponetica(user_input)

    return render_template(
        'feliponetica.html',
        result=result,
        user_input=user_input
    )


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

    if session["role"] == "student":
        return "Access denied"

    return render_template('course.html')

# ============================================================
# MODULES
# ============================================================

@app.route('/module/<module_id>')
def interactive_module(module_id):

    access_error = require_login()
    if access_error:
        return access_error

    if session["role"] == "student":
        return "Access denied"

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
    app.run(debug=True)
