"""
Phantom Pronouns — an ESL game for Spanish speakers.

THE POINT: Spanish frequently drops the subject pronoun (the verb ending
already tells you who) and its object pronouns are single clitic words
attached to the verb. English needs an explicit subject AND a separate
object word every time. The game shows a Spanish sentence with its
"phantom" (missing/implicit) pronouns and has the student supply the
two English words that make it explicit.

Example:
    Spanish given:      "La puerta. Me pegó."
    English to build:   ___ hit ___
    subject options:    I, we, you, they, he, she, it   -> correct: it
    object options:     me, us, you, them, him, her, it -> correct: me

LEVEL 1 IS DATA-DRIVEN
----------------------
Level 1 reads the named tables in
static/data/phantom_pronouns.xlsx at runtime. The verb/schema table
selects a schema, its A/X marks select an accepted subject/object pair,
and the Spanish verb and object-pronoun tables provide the conjugation,
phonetic spelling, and Spanish sentence opening.

TO ADD MORE VERBS: add matching rows to the verb/schema and Spanish verb
tables, and use an existing schema number. No code changes are needed.

DROP-IN INSTRUCTIONS
---------------------
1. pip install openpyxl   (only new dependency)
2. Save this file as: games/phantom_pronouns.py
3. Save the spreadsheet as: static/data/phantom_pronouns.xlsx
4. In app.py, where vocab_bp is imported/registered, add:

        from games.phantom_pronouns import phantom_pronouns_bp
        GAME_BLUEPRINTS = [vocab_bp, phantom_pronouns_bp]

5. Save the matching template as: templates/games/phantom_pronouns.html
6. Create this folder (art is optional — a fallback icon is shown
   until you add real images):
        static/images/phantom_pronouns/
   No audio files are needed either: "Play It in English" and the mic
   step use the browser's built-in English text-to-speech.
7. Visit /phantom-pronouns/game

Level 1 requires the workbook tables. If the workbook is missing or a
required table cannot be read, the game reports a workbook load error
instead of silently serving different exercise data.
"""

import os
import re
import random
import sqlite3
import unicodedata

from flask import Blueprint, render_template, jsonify, request, session, current_app

phantom_pronouns_bp = Blueprint(
    "phantom_pronouns", __name__, url_prefix="/phantom-pronouns"
)

EXCEL_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "static", "data", "phantom_pronouns.xlsx"
))

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
    "he":  ["[ Mi hermano ]", "[ El niño ]", "[ Mi papá ]", "[ El maestro ]"],
    "she": ["[ Mi hermana ]", "[ La niña ]", "[ Mi mamá ]", "[ La maestra ]"],
    "it":  ["[ un objecto]", "[ un animal ]", "[ algo ]", "[ una cosa ]"],
}

DIRECT_OBJECT_WORDS = [
    {"id": "me",   "en": "me",   "phonetic": "[ mi ]"},
    {"id": "us",   "en": "us",   "phonetic": "[ as ]"}, 
    {"id": "you",  "en": "you",  "phonetic": "[ llu ]"},
    {"id": "them", "en": "them", "phonetic": "[ dem ]"},
    {"id": "him",  "en": "him",  "phonetic": "[ jim ]"},
    {"id": "her",  "en": "her",  "phonetic": "[ jr ]"},
    {"id": "it",   "en": "it",   "phonetic": "[ it ]"},
]
DIRECT_OBJECT_WORDS_BY_ID = {o["id"]: o for o in DIRECT_OBJECT_WORDS}

REFLEXIVE_WORDS = [
    {"id": "myself",     "en": "myself",     "phonetic": "[ mai-self ]"},
    {"id": "yourself",   "en": "yourself",   "phonetic": "[ llor-self ]"},
    {"id": "himself",    "en": "himself",    "phonetic": "[ jim-self ]"},
    {"id": "herself",    "en": "herself",    "phonetic": "[ jr-self ]"},
    {"id": "itself",     "en": "itself",     "phonetic": "[ it-self ]"},
    {"id": "ourselves",  "en": "ourselves",  "phonetic": "[ auor-selvs ]"},
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
# ============================================================

LEVELS = [
    {"id": 1, "key": "level_1", "title": "Object Pronouns",
     "category": "direct_object", "clitic": True,
     "eligible_subjects": ["i", "we", "you", "they", "he", "she", "it"],
     "requires_tense_choice": False, "tenses": ["preterite"],
    "blurb": "Use subject-object choices allowed by each verb's schema."},
    {"id": 2, "key": "level_2", "title": "Reflexive Pronouns",
     "category": "reflexive", "clitic": True,
     "eligible_subjects": ["i", "we", "you", "they", "he", "she", "it"],
     "requires_tense_choice": False, "tenses": ["preterite"],
     "blurb": "Choose the subject and reflexive pronoun that fit each Spanish sentence."},
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
AVAILABLE_LEVEL_IDS = {1, 2}

# ============================================================
# LEVELS 2-7 VERB BANKS (unchanged — no spreadsheet for these yet)
# ============================================================

VERB_BANKS = {
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
# LEVEL 1 — EXCEL-DRIVEN VERB & PRONOUN-COMPATIBILITY ENGINE
# ============================================================

def _slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


_level1_cache = None  # Parsed schema, verb, and object-clitic tables.
_level2_cache = None


def _read_workbook_table(worksheets, table_name):
    for worksheet in worksheets:
        if table_name not in worksheet.tables:
            continue
        table = worksheet.tables[table_name]
        rows = worksheet[table.ref]
        headers = [str(cell.value).strip().casefold() for cell in rows[0]]
        records = [
            dict(zip(headers, (cell.value for cell in row)))
            for row in rows[1:]
        ]
        return headers, records
    raise ValueError(f"Workbook table {table_name!r} was not found")


def _table_key(value):
    return str(value).strip().casefold() if value is not None else ""


def _normalized_spanish_form(value):
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _parse_level1_workbook():
    import openpyxl

    workbook = openpyxl.load_workbook(EXCEL_PATH, data_only=True, read_only=False)
    try:
        worksheets = workbook.worksheets
        _, verb_schema_rows = _read_workbook_table(
            worksheets, "verb_schema_refrence"
        )
        _, spanish_verb_rows = _read_workbook_table(
            worksheets, "spanish_verb_refrence"
        )
        _, object_pronoun_rows = _read_workbook_table(
            worksheets, "en_sp_object_pronoun_refrence"
        )

        subjects_by_label = {
            _table_key(subject["en"]): subject["id"]
            for subject in SUBJECT_OPTIONS
        }
        objects_by_label = {
            _table_key(obj["en"]): obj["id"]
            for obj in DIRECT_OBJECT_WORDS
        }

        schemas = {}
        for schema_number in range(1, 6):
            schema_name = f"schema_{schema_number}"
            headers, rows = _read_workbook_table(worksheets, schema_name)
            schema_pairs = []
            for row in rows:
                subject_id = subjects_by_label.get(_table_key(row[headers[0]]))
                if not subject_id:
                    continue
                for object_label in headers[1:]:
                    object_id = objects_by_label.get(_table_key(object_label))
                    if object_id and _table_key(row[object_label]) == "a":
                        schema_pairs.append((subject_id, object_id))
            schemas[schema_number] = schema_pairs

        object_clitics = {}
        for row in object_pronoun_rows:
            object_id = objects_by_label.get(
                _table_key(row["english_object_pronouns"])
            )
            if not object_id:
                continue
            object_clitics[object_id] = {
                _table_key(reference): str(row[reference]).strip()
                for reference in ("s1", "s2", "s3")
                if row.get(reference)
            }

        spanish_by_verb = {}
        spanish_subject_columns = {
            _table_key(subject["en"]): subject["id"]
            for subject in SUBJECT_OPTIONS
        }
        for row in spanish_verb_rows:
            verb_key = _table_key(row["english_verb"])
            if not verb_key:
                continue
            forms = {
                subject_id: str(row[column]).strip()
                for column, subject_id in spanish_subject_columns.items()
                if row.get(column)
            }
            spanish_by_verb.setdefault(verb_key, []).append({
                "gloss": str(row["english_verb"]).strip().lower(),
                "phonetic": str(row["feliponetica"]).strip(),
                "clitic_reference": _table_key(row["object_pronoun_refrence"]),
                "conj": forms,
            })

        references_by_verb = {}
        for row in verb_schema_rows:
            verb_key = _table_key(row["verbs"])
            try:
                schema_number = int(row["schema"])
            except (TypeError, ValueError):
                continue
            references_by_verb.setdefault(verb_key, []).append(schema_number)

        verbs = []
        for verb_key, schema_numbers in references_by_verb.items():
            spanish_forms = spanish_by_verb.get(verb_key, [])
            if not spanish_forms:
                continue
            for index, schema_number in enumerate(schema_numbers):
                if index < len(spanish_forms):
                    spanish_verb = spanish_forms[index]
                elif len(spanish_forms) == 1:
                    spanish_verb = spanish_forms[0]
                else:
                    continue
                if schema_number not in schemas:
                    continue
                verbs.append({
                    **spanish_verb,
                    "id": f"{_slugify(spanish_verb['gloss'])}-schema-{schema_number}-{index}",
                    "schema": schema_number,
                    "hint_image": (
                        "/static/images/phantom_pronouns/verbs/"
                        f"{_slugify(spanish_verb['gloss'])}.webp"
                    ),
                })

        if not verbs or not object_clitics:
            raise ValueError("Workbook tables did not provide usable Level 1 data")
        return {"verbs": verbs, "schemas": schemas, "clitics": object_clitics}
    finally:
        workbook.close()


def _get_level1_data():
    global _level1_cache
    if _level1_cache is None:
        try:
            _level1_cache = _parse_level1_workbook()
        except Exception as error:
            raise RuntimeError(
                f"Could not load the Level 1 phantom pronoun workbook at {EXCEL_PATH}"
            ) from error
    return _level1_cache


def _parse_level2_workbook():
    import openpyxl

    workbook = openpyxl.load_workbook(EXCEL_PATH, data_only=True, read_only=False)
    try:
        worksheets = workbook.worksheets
        _, pronoun_rows = _read_workbook_table(
            worksheets, "lev_2_pronoun_table_1"
        )
        _, verb_rows = _read_workbook_table(worksheets, "lev_2_verb_table_1")
        _, ending_rows = _read_workbook_table(
            worksheets, "lev_2_verb_table_1.1"
        )
        _, translation_rows = _read_workbook_table(
            worksheets, "lev_2_verb_table_1.2"
        )

        subjects_by_label = {
            _table_key(subject["en"]): subject["id"]
            for subject in SUBJECT_OPTIONS
        }
        pronouns = {}
        reflexive_options = []
        for row in pronoun_rows:
            subject_id = subjects_by_label.get(
                _table_key(row["lev_2_pronoun_table_1"])
            )
            if not subject_id:
                continue
            pronoun = {
                "reflexive": str(row["reflexive"]).strip(),
                "phonetic": str(row["reflexive_feliponetica"]).strip(),
                "spanish_pronoun_1": str(row["spanish_pronoun_1"]).strip(),
                "spanish_pronoun_2": str(row["spanish_pronoun_2"]).strip(),
                "help_texts": [
                    str(row[column]).strip()
                    for column in row
                    if column.startswith("spanish_help_text") and row[column]
                ],
            }
            pronouns[subject_id] = pronoun
            reflexive_options.append({
                "id": REFLEXIVE_EN_BY_SUBJECT[subject_id],
                "en": pronoun["reflexive"],
                "phonetic": f"[ {pronoun['phonetic']} ]",
            })

        translations = {
            _table_key(row["verbs"]): row for row in translation_rows
        }
        endings_by_verb = {
            _table_key(row["verbs"]): row for row in ending_rows
        }
        verbs = []
        for row in verb_rows:
            verb_key = _table_key(row["verbs"])
            translation = translations.get(verb_key)
            if not verb_key or not translation:
                continue
            forms = {}
            for label, value in translation.items():
                subject_id = subjects_by_label.get(_table_key(label))
                form = str(value).strip() if value is not None else ""
                if subject_id and form and _table_key(form) != "x":
                    forms[subject_id] = form
            eligible_subjects = [
                subject_id
                for label, value in row.items()
                if (subject_id := subjects_by_label.get(_table_key(label)))
                and _table_key(value) == "a"
                and subject_id in forms
            ]
            if not eligible_subjects:
                continue

            ending_row = endings_by_verb.get(verb_key, {})
            endings = []
            for index in range(1, 6):
                english = ending_row.get(f"extra_end{index}")
                spanish = ending_row.get(f"sp_extra_end{index}")
                if english and _table_key(english) != "x":
                    endings.append({
                        "english": str(english).strip(),
                        "spanish": (
                            str(spanish).strip()
                            if spanish and _table_key(spanish) != "x"
                            else ""
                        ),
                    })

            verbs.append({
                "id": _slugify(verb_key),
                "gloss": str(row["verbs"]).strip().lower(),
                "phonetic": str(ending_row.get("feliponetica") or "").strip(),
                "eligible_subjects": eligible_subjects,
                "forms": forms,
                "pronoun_1_reference": _table_key(
                    translation.get("spanish_pronoun_1_refrence")
                ),
                "pronoun_2_reference": _table_key(
                    translation.get("spanish_pronoun_2_refrence")
                ),
                "endings": endings,
                "hint_image": (
                    "/static/images/phantom_pronouns/verbs/"
                    f"{_slugify(verb_key)}.webp"
                ),
            })

        if not verbs or not pronouns:
            raise ValueError("Workbook tables did not provide usable Level 2 data")
        return {"verbs": verbs, "pronouns": pronouns,
                "reflexive_options": reflexive_options}
    finally:
        workbook.close()


def _get_level2_data():
    global _level2_cache
    if _level2_cache is None:
        try:
            _level2_cache = _parse_level2_workbook()
        except Exception as error:
            raise RuntimeError(
                f"Could not load the Level 2 phantom pronoun workbook at {EXCEL_PATH}"
            ) from error
    return _level2_cache


# ============================================================
# EXERCISE GENERATION
# ============================================================

def _capitalize(word):
    return word[:1].upper() + word[1:] if word else word


def _build_level1_exercise():
    data = _get_level1_data()
    usable_verbs = [
        verb for verb in data["verbs"]
        if any(
            data["clitics"].get(object_id, {}).get(verb["clitic_reference"])
            for _, object_id in data["schemas"].get(verb["schema"], [])
        )
    ]
    if not usable_verbs:
        raise ValueError("No verbs have an accepted subject/object pair in their schema")
    verb = random.choice(usable_verbs)
    accepted_pairs = [
        {"subject_id": subject_id, "object_id": object_id}
        for subject_id, object_id in data["schemas"][verb["schema"]]
        if data["clitics"].get(object_id, {}).get(verb["clitic_reference"])
    ]
    accepted_pair = random.choice(accepted_pairs)
    subject_id = accepted_pair["subject_id"]
    object_id = accepted_pair["object_id"]
    subject = SUBJECTS_BY_ID[subject_id]
    object_word = DIRECT_OBJECT_WORDS_BY_ID[object_id]
    object_es = data["clitics"][object_id][verb["clitic_reference"]]
    conjugated = verb["conj"][subject_id]

    context_line = None
    if subject["conj_group"] == "3rd_singular":
        context_line = random.choice(CONTEXT_NOUNS[subject["gender"]])

    target_clause = f"{_capitalize(object_es)} {conjugated}."
    spanish_prompt = f"{context_line} {target_clause}" if context_line else target_clause
    english_sentence = f"{_capitalize(subject['en'])} {verb['gloss']} {object_word['en']}."

    return {
        "spanish_prompt": spanish_prompt,
        "verb_infinitive": verb["gloss"],
        "verb_phonetic": f"[ {verb['phonetic']} ]",
        "hint_image": verb["hint_image"],
        "subject_options": SUBJECT_OPTIONS,
        "correct_subject_id": subject_id,
        "object_options": DIRECT_OBJECT_WORDS,
        "correct_object_id": object_id,
        "requires_tense_choice": False,
        "tense_options": None,
        "correct_tense_id": None,
        "english_sentence": english_sentence,
    }


_LEVEL2_IT_HELP_TEXT_BY_VERB = {
    "need to wash": "[un animal]",
    "need to dry": "[un animal]",
    "confused": "[algo]",
    "didn't clean": "[un objeto]",
    "cleaned": "[un objeto]",
    "hurt": "[un animal]",
    "cut": "[un animal]",
    "burned": "[un objeto]",
    "injured": "[un animal]",
    "scratched": "[un animal]",
    "adapted": "[una maquina]",
    "pushed": "[un objeto]",
}


def _build_level2_exercise():
    data = _get_level2_data()
    verb = random.choice(data["verbs"])
    subject_id = random.choice(verb["eligible_subjects"])
    subject = SUBJECTS_BY_ID[subject_id]
    pronoun = data["pronouns"][subject_id]
    reflexive_id = REFLEXIVE_EN_BY_SUBJECT[subject_id]
    reflexive = next(
        option for option in data["reflexive_options"]
        if option["id"] == reflexive_id
    )
    spanish_form = verb["forms"][subject_id]
    spanish_parts = []
    if verb["pronoun_1_reference"] == "a":
        spanish_parts.append(pronoun["spanish_pronoun_1"])
    if verb["pronoun_2_reference"] == "a":
        spanish_parts.append(pronoun["spanish_pronoun_2"])
    spanish_parts.append(spanish_form)

    ending = random.choice(verb["endings"]) if verb["endings"] else None
    if ending and ending["spanish"]:
        spanish_parts.append(ending["spanish"])
    spanish_clause = " ".join(part for part in spanish_parts if part)

    gender_subjects = ["he", "she", "it"]
    matching_gender_subjects = [
        candidate for candidate in gender_subjects
        if candidate in verb["eligible_subjects"]
        and _normalized_spanish_form(verb["forms"].get(candidate, ""))
        == _normalized_spanish_form(spanish_form)
    ]
    context_line = None
    if subject_id in matching_gender_subjects and len(matching_gender_subjects) > 1:
        help_texts = pronoun["help_texts"]
        if subject_id == "it":
            preferred = _LEVEL2_IT_HELP_TEXT_BY_VERB.get(verb["gloss"])
            context_line = next(
                (text for text in help_texts if text.casefold() == (preferred or "").casefold()),
                help_texts[0] if help_texts else None,
            )
        elif help_texts:
            context_line = random.choice(help_texts)
    if context_line:
        spanish_clause = f"{context_line} {spanish_clause}"

    english_parts = [subject["en"], verb["gloss"], reflexive["en"]]
    if ending:
        english_parts.append(ending["english"])
    english_sentence = f"{_capitalize(' '.join(english_parts))}."

    return {
        "spanish_prompt": f"{_capitalize(spanish_clause)}.",
        "verb_infinitive": verb["gloss"],
        "verb_phonetic": f"[ {verb['phonetic']} ]",
        "hint_image": verb["hint_image"],
        "subject_options": SUBJECT_OPTIONS,
        "correct_subject_id": subject_id,
        "object_options": data["reflexive_options"],
        "correct_object_id": reflexive_id,
        "requires_tense_choice": False,
        "tense_options": None,
        "correct_tense_id": None,
        "english_sentence": english_sentence,
    }


def _object_chip_pool_and_correct(level, subject_id):
    """Returns (chip_pool, correct_object_id, spanish_word_for_clue) for levels 2-7."""
    category = level["category"]

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


def _build_other_level_exercise(level_id):
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


def build_exercise(level_id):
    if level_id == 1:
        return _build_level1_exercise()
    if level_id == 2:
        return _build_level2_exercise()
    return _build_other_level_exercise(level_id)


def build_exercise_set(level_id, count=EXERCISES_PER_ROUND):
    return [build_exercise(level_id) for _ in range(count)]


def build_review_set(completed_level_ids, count=EXERCISES_PER_ROUND):
    pool = [lid for lid in completed_level_ids if lid in AVAILABLE_LEVEL_IDS]
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
        if lv["id"] in AVAILABLE_LEVEL_IDS
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

    if level_id not in AVAILABLE_LEVEL_IDS:
        return jsonify({"error": "Level not available"}), 404

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
