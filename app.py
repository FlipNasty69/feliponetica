import nltk
import re

from flask import Flask, render_template, request, send_from_directory, abort
from g2p_en import G2p
from flask import session, redirect, url_for

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change this

USERS = {
    "felipe": {"password": "stopplayin", "role": "admin"},
    "karina": {"password": "i knew it", "role": "admin"},
    "student": {"password": "i sent the song", "role": "student"}
}

# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = USERS.get(username)

        if user and user["password"] == password:
            session["username"] = username
            session["role"] = user["role"]
            return redirect(url_for("home"))
        else:
            return "Invalid credentials"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


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
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("index.html")



# ============================================================
# FELIPONETICA
# ============================================================

@app.route('/feliponetica', methods=['GET', 'POST'])
def feliponetica():

    if "role" not in session or session["role"] not in ["student", "admin"]:
        return "Access denied"

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
            "small = pequeño"
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
            "take = tomar / llevar"
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
    }

}


# ============================================================
# VOCABULARY PAGE
# ============================================================

@app.route('/vocab_drill')
def vocab():

    if "role" not in session or session["role"] not in ["student", "admin"]:
        return "Access denied"

    return render_template(
        'vocab_drill.html',
        vocabulary_sets=VOCABULARY_SETS
    )


# ============================================================
# LESSONS
# ============================================================

@app.route('/lessons')
def lessons():

    if "role" not in session or session["role"] not in ["student", "admin"]:
        return "Access denied"

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

    # ADMIN ONLY
    if "role" not in session or session["role"] != "admin":
        return "Access denied"

    return render_template('course.html')

# ============================================================
# ABOUT
# ============================================================

@app.route('/about')
def about():
    return render_template('about.html')


# ============================================================
# LIVE CLASSES
# ============================================================

@app.route('/live-classes')
def live_classes():
    return render_template('live_classes.html')


# ============================================================
# CONTACT
# ============================================================

@app.route('/contact')
def contact():
    return render_template('contact.html')


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)