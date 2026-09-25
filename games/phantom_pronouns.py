"""
Phantom Pronouns — an ESL game for Spanish speakers.

THE POINT: Spanish frequently drops the subject pronoun (the verb ending
already tells you who) and its object pronouns are single clitic words
attached to the verb. English needs an explicit subject AND a separate
object word every time. The game shows a Spanish sentence with its
"phantom" (missing/implicit) pronouns and has the student supply the
two English words that make it explicit.

Example (this is exactly the shape the front end renders):
    Spanish given:      "Mugre puerta. Me pegó."
    English to build:   ___ hit ___
    subject options:    I, we, you, they, he, she, it   -> correct: it
    object options:     me, us, you, them, him, her, it -> correct: me

DROP-IN INSTRUCTIONS
---------------------
1. Save this file as: games/phantom_pronouns.py   (next to games/vocab_game.py)
2. In app.py, where vocab_bp is imported/registered, add:

        from games.phantom_pronouns import phantom_pronouns_bp
        GAME_BLUEPRINTS = [vocab_bp, phantom_pronouns_bp]

3. Save the matching template as: templates/games/phantom_pronouns.html
4. Create this folder (it can start empty — a built-in fallback icon
   is shown until you add real art):
        static/images/phantom_pronouns/
   No audio files are needed: "Play the Sentence" and the mic step use
   the browser's built-in English text-to-speech, so pronunciation
   practice works immediately. Swap in real recordings later by
   editing speakEnglish() in the template.
5. Visit /phantom-pronouns/game

CONTENT
-------
Level 1 (direct object pronouns) ships with six fully-worked verbs.
Levels 2-7 each ship with one worked verb so the whole progression —
reciprocal, reflexive, distributive, indefinite x3, plus the Review
module — is playable end to end today. Add more verbs to each
VERB_BANKS[n] entry the same way as you produce art/audio.
"""

import os
import random
import sqlite3

from flask import Blueprint, render_template, jsonify, request, session, current_app

phantom_pronouns_bp = Blueprint(
    "phantom_pronouns", __name__, url_prefix="/phantom-pronouns"
)

# ============================================================
# ENGLISH ANSWER SETS
# (These are what the student clicks/fills in. "phonetic" is a
#  feliponetica-style pronunciation guide for the English word.)
# ============================================================

# conj_group tells the generator which Spanish verb ending to pull.
# "3rd_singular" is the ambiguous one (él/ella/ello share one ending),
# so those three need a context sentence to disambiguate — see
# CONTEXT_NOUNS below.
SUBJECT_OPTIONS = [
    {"id": "i",    "en": "I",    "conj_group": "yo",           "phonetic": "[ ai ]"},
    {"id": "we",   "en": "we",   "conj_group": "nosotros",     "phonetic": "[ wi ]"},
    {"id": "you",  "en": "you",  "conj_group": "tu",           "phonetic": "[ llu ]"},
    {"id": "they", "en": "they", "conj_group": "ellos",        "phonetic": "[ dei ]"},
    {"id": "he",   "en": "he",   "conj_group": "3rd_singular", "gender": "he",  "phonetic": "[ ji ]"},
    {"id": "she",  "en": "she",  "conj_group": "3rd_singular", "gender": "she", "phonetic": "[ shi ]"},
    {"id": "it",   "en": "it",   "conj_group": "3rd_singular", "gender": "it",  "phonetic": "[ it ]"},
]
SUBJECTS_BY_ID = {p["id"]: p for p in SUBJECT_OPTIONS}

# Short Spanish phrases that establish the missing gender/animacy when
# the verb ending alone can't tell you if it's "he", "she", or "it".
CONTEXT_NOUNS = {
    "he":  ["Mi hermano.", "El niño.", "Mi papá.", "El maestro."],
    "she": ["Mi hermana.", "La niña.", "Mi mamá.", "La maestra."],
    "it":  ["La puerta.", "El carro.", "La pelota.", "El teléfono.", "La silla."],
}

# The base object-pronoun pool (direct objects). Other categories mix
# these in as distractors alongside their own special words.
DIRECT_OBJECT_WORDS = [
    {"id": "me",   "en": "me",   "es": "me",  "phonetic": "[ mi ]"},
    {"id": "us",   "en": "us",   "es": "nos", "phonetic": "[ os ]"},
    {"id": "you",  "en": "you",  "es": "te",  "phonetic": "[ llu ]"},
    {"id": "them", "en": "them", "es": "los", "phonetic": "[ dem ]"},
    {"id": "him",  "en": "him",  "es": "lo",  "phonetic": "[ jim ]"},
    {"id": "her",  "en": "her",  "es": "la",  "phonetic": "[ jer ]"},
    {"id": "it",   "en": "it",   "es": "lo",  "phonetic": "[ it ]"},
]
# Avoid trivially reflexive-sounding pairs in level 1 (subject "I" + object "me").
SELF_OBJECT_ID_BY_SUBJECT = {
    "i": "me", "we": "us", "you": "you", "they": "them",
    "he": "him", "she": "her", "it": "it",
}

REFLEXIVE_WORDS = [
    {"id": "myself",     "en": "myself",     "phonetic": "[ mai-self ]"},
    {"id": "yourself",   "en": "yourself",   "phonetic": "[ ior-self ]"},
    {"id": "himself",    "en": "himself",    "phonetic": "[ jim-self ]"},
    {"id": "herself",    "en": "herself",    "phonetic": "[ jer-self ]"},
    {"id": "itself",     "en": "itself",     "phonetic": "[ it-self ]"},
    {"id": "ourselves",  "en": "ourselves",  "phonetic": "[ aur-selvs ]"},
    {"id": "themselves", "en": "themselves", "phonetic": "[ dem-selvs ]"},
]
REFLEXIVE_EN_BY_SUBJECT = {
    "i": "myself", "you": "yourself", "he": "himself", "she": "herself",
    "it": "itself", "we": "ourselves", "they": "themselves",
}
REFLEXIVE_ES_CLITIC_BY_SUBJECT = {
    "i": "me", "you": "te", "he": "se", "she": "se", "it": "se",
    "we": "nos", "they": "se",
}

EACH_OTHER_WORD = {"id": "each_other", "en": "each other", "phonetic": "[ ich A-der ]"}
RECIPROCAL_ES_CLITIC_BY_SUBJECT = {"we": "nos", "they": "se"}  # only plural subjects qualify

# Standalone object-ish word banks for levels 4-7 (not mixed with direct objects).
OBJECT_SETS = {
    "distributive": [
        {"id": "each_one", "en": "each one", "es": "cada uno", "phonetic": "[ ich uan ]"},
        {"id": "both",     "en": "both",     "es": "ambos",    "phonetic": "[ boaz ]"},
        {"id": "all",      "en": "all",      "es": "todos",    "phonetic": "[ ol ]"},
        {"id": "none",     "en": "none",     "es": "ninguno",  "phonetic": "[ nan ]"},
    ],
    "indefinite_singular": [
        {"id": "someone",   "en": "someone",   "es": "alguien", "phonetic": "[ som-uan ]"},
        {"id": "no_one",    "en": "no one",    "es": "nadie",   "phonetic": "[ no-uan ]"},
        {"id": "something", "en": "something", "es": "algo",    "phonetic": "[ som-zing ]"},
        {"id": "nothing",   "en": "nothing",   "es": "nada",    "phonetic": "[ na-zing ]"},
    ],
    "indefinite_plural": [
        {"id": "some",    "en": "some",    "es": "algunos", "phonetic": "[ som ]"},
        {"id": "several", "en": "several", "es": "varios",  "phonetic": "[ se-ve-ral ]"},
        {"id": "a_few",   "en": "a few",   "es": "unos",    "phonetic": "[ e fiu ]"},
        {"id": "all_p",   "en": "all",     "es": "todos",   "phonetic": "[ ol ]"},
    ],
    "indefinite_flexible": [
        {"id": "any_one",    "en": "any one",     "es": "cualquiera",   "phonetic": "[ e-ni uan ]"},
        {"id": "any_of_them","en": "any of them", "es": "cualesquiera", "phonetic": "[ e-ni ov dem ]"},
    ],
}

TENSE_GLOSS = {
    "preterite": {"label": "Past",    "es": "Pasado"},
    "present":   {"label": "Present", "es": "Presente"},
    "future":    {"label": "Future",  "es": "Futuro"},
}

# ============================================================
# LEVEL CONFIG
# clitic=True  -> in the Spanish clue, the pronoun word sits BEFORE the verb
#                 (me/te/lo/la/nos/los/se — direct object, reflexive, reciprocal)
# clitic=False -> the pronoun phrase sits AFTER the verb, with "a"
#                 (cada uno, alguien... — distributive/indefinite)
# ============================================================

LEVELS = [
    {"id": 1, "key": "level_1", "title": "Direct Object Pronouns",
     "category": "direct_object", "clitic": True,
     "eligible_subjects": ["i", "we", "you", "they", "he", "she", "it"],
     "requires_tense_choice": False, "tenses": ["preterite"],
     "blurb": "Spanish drops the subject and glues the object onto the verb. Unglue both into English."},
    {"id": 2, "key": "level_2", "title": "Reciprocal Pronouns",
     "category": "reciprocal", "clitic": True,
     "eligible_subjects": ["we", "they"],
     "requires_tense_choice": True, "tenses": ["preterite", "present"],
     "blurb": "\"Se ayudan\" = they help each other. Only plural subjects qualify — and you pick the tense."},
    {"id": 3, "key": "level_3", "title": "Reflexive Pronouns",
     "category": "reflexive", "clitic": True,
     "eligible_subjects": ["i", "we", "you", "they", "he", "she", "it"],
     "requires_tense_choice": False, "tenses": ["preterite", "present", "future"],
     "blurb": "When the subject does it to itself: me lavo -> I wash myself."},
    {"id": 4, "key": "level_4", "title": "Distributive Pronouns",
     "category": "distributive", "clitic": False,
     "eligible_subjects": ["i", "we", "you", "they", "he", "she", "it"],
     "requires_tense_choice": False, "tenses": ["present"],
     "blurb": "Cada uno, ambos, todos, ninguno — each one, both, all, none."},
    {"id": 5, "key": "level_5", "title": "Indefinite Pronouns (Singular)",
     "category": "indefinite_singular", "clitic": False,
     "eligible_subjects": ["i", "we", "you", "they", "he", "she", "it"],
     "requires_tense_choice": False, "tenses": ["present"],
     "blurb": "Alguien, nadie, algo, nada — someone, no one, something, nothing."},
    {"id": 6, "key": "level_6", "title": "Indefinite Pronouns (Plural)",
     "category": "indefinite_plural", "clitic": False,
     "eligible_subjects": ["i", "we", "you", "they", "he", "she", "it"],
     "requires_tense_choice": False, "tenses": ["present"],
     "blurb": "Algunos, varios, unos, todos — some, several, a few, all."},
    {"id": 7, "key": "level_7", "title": "Indefinite Pronouns (Flexible)",
     "category": "indefinite_flexible", "clitic": False,
     "eligible_subjects": ["i", "we", "you", "they", "he", "she", "it"],
     "requires_tense_choice": False, "tenses": ["present"],
     "blurb": "Cualquiera / cualesquiera — pronouns that don't care about number."},
]
LEVELS_BY_ID = {lv["id"]: lv for lv in LEVELS}

# ============================================================
# VERB BANKS (add more verbs per level as you produce assets)
# Every verb's "conj" is keyed [tense][conj_group]; "gloss"/"phonetic"
# are keyed by tense so the English side reads naturally.
# ============================================================

VERB_BANKS = {
    1: [
        {"id": "pegar", "gloss": {"preterite": "hit"}, "phonetic": {"preterite": "[ jit ]"},
         "conj": {"preterite": {"yo": "pegué", "tu": "pegaste", "nosotros": "pegamos",
                                 "ellos": "pegaron", "3rd_singular": "pegó"}},
         "hint_image": "/static/images/phantom_pronouns/pegar.webp"},
        {"id": "ayudar", "gloss": {"preterite": "helped"}, "phonetic": {"preterite": "[ jelpt ]"},
         "conj": {"preterite": {"yo": "ayudé", "tu": "ayudaste", "nosotros": "ayudamos",
                                 "ellos": "ayudaron", "3rd_singular": "ayudó"}},
         "hint_image": "/static/images/phantom_pronouns/ayudar.webp"},
        {"id": "ver", "gloss": {"preterite": "saw"}, "phonetic": {"preterite": "[ so ]"},
         "conj": {"preterite": {"yo": "vi", "tu": "viste", "nosotros": "vimos",
                                 "ellos": "vieron", "3rd_singular": "vio"}},
         "hint_image": "/static/images/phantom_pronouns/ver.webp"},
        {"id": "llamar", "gloss": {"preterite": "called"}, "phonetic": {"preterite": "[ cold ]"},
         "conj": {"preterite": {"yo": "llamé", "tu": "llamaste", "nosotros": "llamamos",
                                 "ellos": "llamaron", "3rd_singular": "llamó"}},
         "hint_image": "/static/images/phantom_pronouns/llamar.webp"},
        {"id": "buscar", "gloss": {"preterite": "looked for"}, "phonetic": {"preterite": "[ lukt for ]"},
         "conj": {"preterite": {"yo": "busqué", "tu": "buscaste", "nosotros": "buscamos",
                                 "ellos": "buscaron", "3rd_singular": "buscó"}},
         "hint_image": "/static/images/phantom_pronouns/buscar.webp"},
        {"id": "amar", "gloss": {"preterite": "loved"}, "phonetic": {"preterite": "[ lavd ]"},
         "conj": {"preterite": {"yo": "amé", "tu": "amaste", "nosotros": "amamos",
                                 "ellos": "amaron", "3rd_singular": "amó"}},
         "hint_image": "/static/images/phantom_pronouns/amar.webp"},
    ],
    2: [
        {"id": "ver_rec", "gloss": {"preterite": "saw", "present": "see"},
         "phonetic": {"preterite": "[ so ]", "present": "[ si ]"},
         "conj": {"preterite": {"nosotros": "vimos", "ellos": "vieron"},
                  "present": {"nosotros": "vemos", "ellos": "ven"}},
         "hint_image": "/static/images/phantom_pronouns/ver_reciprocal.webp"},
        {"id": "ayudar_rec", "gloss": {"preterite": "helped", "present": "help"},
         "phonetic": {"preterite": "[ jelpt ]", "present": "[ jelp ]"},
         "conj": {"preterite": {"nosotros": "ayudamos", "ellos": "ayudaron"},
                  "present": {"nosotros": "ayudamos", "ellos": "ayudan"}},
         "hint_image": "/static/images/phantom_pronouns/ayudar_reciprocal.webp"},
    ],
    3: [
        {"id": "lavar_refl",
         "gloss": {"present": "wash", "preterite": "washed", "future": "will wash"},
         "phonetic": {"present": "[ uash ]", "preterite": "[ uasht ]", "future": "[ uil uash ]"},
         "conj": {
             "present":   {"yo": "lavo",   "tu": "lavas",   "nosotros": "lavamos",  "ellos": "lavan",   "3rd_singular": "lava"},
             "preterite": {"yo": "lavé",   "tu": "lavaste", "nosotros": "lavamos",  "ellos": "lavaron", "3rd_singular": "lavó"},
             "future":    {"yo": "lavaré", "tu": "lavarás", "nosotros": "lavaremos","ellos": "lavarán", "3rd_singular": "lavará"},
         },
         "hint_image": "/static/images/phantom_pronouns/lavar.webp"},
    ],
    4: [
        {"id": "dar_dist", "gloss": {"present": "give a gift to"}, "phonetic": {"present": "[ guiv e guift tu ]"},
         "conj": {"present": {"yo": "doy", "tu": "das", "nosotros": "damos",
                               "ellos": "dan", "3rd_singular": "da"}},
         "hint_image": "/static/images/phantom_pronouns/dar.webp"},
    ],
    5: [
        {"id": "ver_indef_s", "gloss": {"present": "see"}, "phonetic": {"present": "[ si ]"},
         "conj": {"present": {"yo": "veo", "tu": "ves", "nosotros": "vemos",
                               "ellos": "ven", "3rd_singular": "ve"}},
         "hint_image": "/static/images/phantom_pronouns/ver.webp"},
    ],
    6: [
        {"id": "comprar_indef_p", "gloss": {"present": "buy"}, "phonetic": {"present": "[ bai ]"},
         "conj": {"present": {"yo": "compro", "tu": "compras", "nosotros": "compramos",
                               "ellos": "compran", "3rd_singular": "compra"}},
         "hint_image": "/static/images/phantom_pronouns/comprar.webp"},
    ],
    7: [
        {"id": "elegir_flex", "gloss": {"present": "choose"}, "phonetic": {"present": "[ chus ]"},
         "conj": {"present": {"yo": "elijo", "tu": "eliges", "nosotros": "elegimos",
                               "ellos": "eligen", "3rd_singular": "elige"}},
         "hint_image": "/static/images/phantom_pronouns/elegir.webp"},
    ],
}

EXERCISES_PER_ROUND = 10


# ============================================================
# EXERCISE GENERATION
# ============================================================

def _capitalize(word):
    return word[:1].upper() + word[1:] if word else word


def _object_chip_pool_and_correct(level, subject_id):
    """Returns (chip_pool, correct_object_id, spanish_word_for_clue)."""
    category = level["category"]

    if category == "direct_object":
        pool = DIRECT_OBJECT_WORDS
        avoid_id = SELF_OBJECT_ID_BY_SUBJECT.get(subject_id)
        choices = [w for w in pool if w["id"] != avoid_id] or pool
        chosen = random.choice(choices)
        return pool, chosen["id"], chosen["es"]

    if category == "reciprocal":
        pool = DIRECT_OBJECT_WORDS + [EACH_OTHER_WORD]
        return pool, "each_other", RECIPROCAL_ES_CLITIC_BY_SUBJECT[subject_id]

    if category == "reflexive":
        pool = DIRECT_OBJECT_WORDS + REFLEXIVE_WORDS
        correct_id = REFLEXIVE_EN_BY_SUBJECT[subject_id]
        return pool, correct_id, REFLEXIVE_ES_CLITIC_BY_SUBJECT[subject_id]

    # distributive / indefinite_* — standalone pools, subject-independent
    pool = OBJECT_SETS[category]
    chosen = random.choice(pool)
    return pool, chosen["id"], chosen["es"]


def build_exercise(level_id):
    level = LEVELS_BY_ID[level_id]
    verb = random.choice(VERB_BANKS[level_id])
    subject_id = random.choice(level["eligible_subjects"])
    subject = SUBJECTS_BY_ID[subject_id]
    conj_group = subject["conj_group"]

    tense = random.choice([t for t in level["tenses"] if t in verb["conj"]])
    conjugated = verb["conj"][tense][conj_group]
    verb_en = verb["gloss"][tense]
    verb_phonetic = verb["phonetic"][tense]

    object_pool, correct_object_id, object_es = _object_chip_pool_and_correct(level, subject_id)
    object_lookup = {o["id"]: o for o in object_pool}
    correct_object = object_lookup[correct_object_id]

    context_line = None
    if conj_group == "3rd_singular":
        context_line = random.choice(CONTEXT_NOUNS[subject["gender"]])

    if level["clitic"]:
        target_clause = f"{_capitalize(object_es)} {conjugated}."
    else:
        target_clause = f"{_capitalize(conjugated)} a {object_es}."

    spanish_prompt = f"{context_line} {target_clause}" if context_line else target_clause
    english_sentence = f"{_capitalize(subject['en'])} {verb_en} {correct_object['en']}."

    return {
        "spanish_prompt": spanish_prompt,
        "verb_infinitive": verb_en,
        "verb_phonetic": verb_phonetic,
        "hint_image": verb["hint_image"],
        "subject_options": SUBJECT_OPTIONS,
        "correct_subject_id": subject_id,
        "object_options": object_pool,
        "correct_object_id": correct_object_id,
        "requires_tense_choice": level["requires_tense_choice"],
        "tense_options": (
            [{"id": t, **TENSE_GLOSS[t]} for t in level["tenses"]]
            if level["requires_tense_choice"] else None
        ),
        "correct_tense_id": tense if level["requires_tense_choice"] else None,
        "english_sentence": english_sentence,
    }


def build_exercise_set(level_id, count=EXERCISES_PER_ROUND):
    return [build_exercise(level_id) for _ in range(count)]


def build_review_set(completed_level_ids, count=EXERCISES_PER_ROUND):
    pool = [lid for lid in completed_level_ids if lid in LEVELS_BY_ID]
    if not pool:
        return []
    return [build_exercise(random.choice(pool)) for _ in range(count)]


# ============================================================
# PROGRESS (sqlite, same db file the rest of the site already uses)
# ============================================================

def _db_path():
    return os.path.join(current_app.root_path, "student_users.db")


def _ensure_progress_table(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS phantom_pronouns_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            level_key TEXT NOT NULL,
            best_score INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, level_key)
        )
    """)


# ============================================================
# ROUTES — PAGE
# ============================================================

@phantom_pronouns_bp.route("/game")
def game_page():
    return render_template("games/phantom_pronouns.html")


# ============================================================
# ROUTES — API
# ============================================================

@phantom_pronouns_bp.route("/api/levels", methods=["GET"])
def get_levels():
    return jsonify([
        {"id": lv["id"], "key": lv["key"], "title": lv["title"],
         "blurb": lv["blurb"], "category": lv["category"]}
        for lv in LEVELS
    ])


@phantom_pronouns_bp.route("/api/progress", methods=["GET"])
def get_progress():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"saved": False, "progress": {}})

    with sqlite3.connect(_db_path()) as connection:
        _ensure_progress_table(connection)
        rows = connection.execute(
            "SELECT level_key, best_score, completed FROM phantom_pronouns_progress WHERE user_id = ?",
            (user_id,),
        ).fetchall()

    progress = {row[0]: {"best_score": row[1], "completed": bool(row[2])} for row in rows}
    return jsonify({"saved": True, "progress": progress})


@phantom_pronouns_bp.route("/api/exercise-set", methods=["GET"])
def get_exercise_set():
    level_param = request.args.get("level", "")
    count = min(max(int(request.args.get("count", EXERCISES_PER_ROUND)), 1), 25)

    if level_param == "review":
        completed_raw = request.args.get("completed", "")
        completed_ids = [int(x) for x in completed_raw.split(",") if x.strip().isdigit()]
        exercises = build_review_set(completed_ids, count)
        if not exercises:
            return jsonify({"error": "No completed levels to review yet."}), 400
        return jsonify(exercises)

    try:
        level_id = int(level_param)
    except ValueError:
        return jsonify({"error": "Invalid level"}), 400

    if level_id not in LEVELS_BY_ID:
        return jsonify({"error": "Level not found"}), 404

    session["pp_active_level"] = level_id
    return jsonify(build_exercise_set(level_id, count))


@phantom_pronouns_bp.route("/api/submit-score", methods=["POST"])
def submit_score():
    payload = request.get_json(silent=True) or {}
    level_key = str(payload.get("level_key", "")).strip()
    score = max(0, int(payload.get("score", 0)))
    completed = bool(payload.get("completed", False))

    if not level_key:
        return jsonify({"error": "level_key is required"}), 400

    user_id = session.get("user_id")
    if not user_id:
        # Guest: nothing to persist server-side; the front end keeps
        # guest progress in localStorage so redo/scoring still works.
        return jsonify({"saved": False})

    with sqlite3.connect(_db_path()) as connection:
        _ensure_progress_table(connection)
        existing = connection.execute(
            "SELECT best_score, completed FROM phantom_pronouns_progress WHERE user_id = ? AND level_key = ?",
            (user_id, level_key),
        ).fetchone()
        best_score = max(score, existing[0]) if existing else score
        was_completed = bool(existing[1]) if existing else False
        connection.execute("""
            INSERT INTO phantom_pronouns_progress (user_id, level_key, best_score, completed)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, level_key) DO UPDATE SET
                best_score = excluded.best_score,
                completed = excluded.completed
        """, (user_id, level_key, best_score, int(completed or was_completed)))
        connection.commit()

    return jsonify({"saved": True, "best_score": best_score})


@phantom_pronouns_bp.route("/api/verify-voice", methods=["POST"])
def verify_voice():
    """Receives the 'now you say it' recording. Mock verification, mirrors vocab_game."""
    if "audio" not in request.files:
        return jsonify({"received": False, "message": "No audio file uploaded."}), 400

    audio_file = request.files["audio"]
    temp_dir = "temp_audio"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, "phantom_pronouns_attempt.wav")
    audio_file.save(temp_path)

    if os.path.exists(temp_path):
        os.remove(temp_path)

    return jsonify({"received": True, "status": "Audio processed successfully."})
