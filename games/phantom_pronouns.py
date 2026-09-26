"""
Phantom Pronouns — an ESL game for Spanish speakers.

THE POINT: Spanish frequently drops the subject pronoun (the verb ending
already tells you who) and its object pronouns are single clitic words
attached to the verb. English needs an explicit subject AND a separate
object word every time. The game shows a Spanish sentence with its
"phantom" (missing/implicit) pronouns and has the student supply the
two English words that make it explicit.

Example:
    Spanish given:      "Mugre puerta. Me pegó."
    English to build:   ___ hit ___
    subject options:    I, we, you, they, he, she, it   -> correct: it
    object options:     me, us, you, them, him, her, it -> correct: me

LEVEL 1 IS DATA-DRIVEN
-----------------------
Level 1 no longer ships a hand-typed verb list. Instead it reads
static/data/phantom_pronouns_lev_1.xlsx at runtime and builds:
  - every verb's full preterite conjugation (from just the "yo" form,
    using a regular-preterite engine + a short irregular-verb override
    table — see conjugate_preterite())
  - which Spanish object clitic(s) are even grammatical for a given
    subject+object pair, and which alternate spellings exist (te/le/lo/la
    for "you", le/lo for "him", etc.) — read straight from the sheet's
    subject/object compatibility table
  - which verbs are "dative" verbs (llamar, preguntar, decir, dar,
    mostrar, pagar, prestar, devolver, confiar, agradecer, recordar,
    prometer...) that take le/les instead of lo/la/los/las for a 3rd
    person object — read from the sheet's "X" / "as indirect object"
    markings

With ~99 verbs x up to 7 subjects x up to 7 objects x multiple valid
clitic spellings x multiple disambiguating context sentences, level 1
alone generates many thousands of distinct exercises, and every one of
those choices (verb, subject, object, clitic spelling, context line,
tense where relevant) is picked at random per exercise.

TO ADD MORE VERBS: just add rows to the spreadsheet's verb table
following the existing columns. No code changes needed.

DROP-IN INSTRUCTIONS
---------------------
1. pip install openpyxl   (only new dependency)
2. Save this file as: games/phantom_pronouns.py
3. Save the spreadsheet as: static/data/phantom_pronouns_lev_1.xlsx
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

If the spreadsheet is missing or fails to parse, level 1 quietly falls
back to a small built-in seed list (see _FALLBACK_LEVEL1_VERBS) instead
of crashing the page.
"""

import os
import re
import random
import sqlite3

from flask import Blueprint, render_template, jsonify, request, session, current_app

phantom_pronouns_bp = Blueprint(
    "phantom_pronouns", __name__, url_prefix="/phantom-pronouns"
)

EXCEL_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "static", "data", "phantom_pronouns_lev_1.xlsx"
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
    "he":  ["Mi hermano.", "El niño.", "Mi papá.", "El maestro."],
    "she": ["Mi hermana.", "La niña.", "Mi mamá.", "La maestra."],
    "it":  ["La puerta.", "El carro.", "La pelota.", "El teléfono.", "La silla."],
}

DIRECT_OBJECT_WORDS = [
    {"id": "me",   "en": "me",   "phonetic": "[ mi ]"},
    {"id": "us",   "en": "us",   "phonetic": "[ os ]"},
    {"id": "you",  "en": "you",  "phonetic": "[ llu ]"},
    {"id": "them", "en": "them", "phonetic": "[ dem ]"},
    {"id": "him",  "en": "him",  "phonetic": "[ jim ]"},
    {"id": "her",  "en": "her",  "phonetic": "[ jer ]"},
    {"id": "it",   "en": "it",   "phonetic": "[ it ]"},
]
DIRECT_OBJECT_WORDS_BY_ID = {o["id"]: o for o in DIRECT_OBJECT_WORDS}

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
# ============================================================

LEVELS = [
    {"id": 1, "key": "level_1", "title": "Direct Object Pronouns",
     "category": "direct_object", "clitic": True,
     "eligible_subjects": ["i", "we", "you", "they", "he", "she", "it"],
     "requires_tense_choice": False, "tenses": ["preterite"],
     "blurb": "Spanish drops the subject and glues the object onto the verb. Unglue both into English. 99+ verbs, all random."},
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

# A handful of genuinely irregular Spanish preterites can't be derived
# from a suffix rule. Keyed by the accent-stripped, lowercased "yo" form.
_IRREGULAR_PRETERITE = {
    "vi":       {"yo": "vi",       "tu": "viste",     "nosotros": "vimos",     "ellos": "vieron",     "3rd_singular": "vio"},
    "oi":       {"yo": "oí",       "tu": "oíste",     "nosotros": "oímos",     "ellos": "oyeron",     "3rd_singular": "oyó"},
    "dije":     {"yo": "dije",     "tu": "dijiste",   "nosotros": "dijimos",   "ellos": "dijeron",    "3rd_singular": "dijo"},
    "di":       {"yo": "di",       "tu": "diste",     "nosotros": "dimos",     "ellos": "dieron",     "3rd_singular": "dio"},
    "traje":    {"yo": "traje",    "tu": "trajiste",  "nosotros": "trajimos",  "ellos": "trajeron",   "3rd_singular": "trajo"},
    "distraje": {"yo": "distraje", "tu": "distrajiste","nosotros": "distrajimos","ellos": "distrajeron","3rd_singular": "distrajo"},
    "detuve":   {"yo": "detuve",   "tu": "detuviste", "nosotros": "detuvimos", "ellos": "detuvieron", "3rd_singular": "detuvo"},
    "segui":    {"yo": "seguí",    "tu": "seguiste",  "nosotros": "seguimos",  "ellos": "siguieron",  "3rd_singular": "siguió"},
    "senti":    {"yo": "sentí",    "tu": "sentiste",  "nosotros": "sentimos",  "ellos": "sintieron",  "3rd_singular": "sintió"},
    "heri":     {"yo": "herí",     "tu": "heriste",   "nosotros": "herimos",   "ellos": "hirieron",   "3rd_singular": "hirió"},
    "preferi":  {"yo": "preferí",  "tu": "preferiste","nosotros": "preferimos","ellos": "prefirieron","3rd_singular": "prefirió"},
    "quise":    {"yo": "quise",    "tu": "quisiste",  "nosotros": "quisimos",  "ellos": "quisieron",  "3rd_singular": "quiso"},
}

# Best-effort feliponetica pronunciation guides for the English glosses
# that ship in the spreadsheet. A verb the teacher adds later that isn't
# in here just falls back to showing the plain English word in brackets
# — add an entry here any time to sharpen it.
_PHONETIC_OVERRIDES = {
    "saw": "so", "heard": "jerd", "looked at": "lukt at", "noticed": "no-tist",
    "recognized": "re-cog-naizd", "found": "faund", "caught": "cot",
    "followed": "fo-loud", "felt": "felt", "observed": "ob-servd",
    "smelled": "smeld", "tracked": "trakt", "identified": "ai-den-ti-faid",
    "discovered": "dis-co-verd", "ignored": "ig-nord", "asked": "askt",
    "said": "sed", "called": "cold", "sent": "sent", "answered": "an-serd",
    "invited": "in-vai-tid", "greeted": "gri-tid", "informed": "in-formd",
    "advised": "ad-vaizd", "taught": "tot", "promised": "pra-mist",
    "remembered": "ri-mem-berd", "interrupted": "in-te-rap-tid",
    "encouraged": "en-ker-ejd", "congratulated": "con-grach-u-lei-tid",
    "blamed": "bleimd", "forgave": "for-gueiv", "received": "ri-sivd",
    "challenged": "cha-lenjd", "thanked": "zankt", "bit": "bit", "cut": "cat",
    "pushed": "pusht", "pulled": "puld", "hit": "jit", "kicked": "kikt",
    "hugged": "jagd", "kissed": "kist", "grabbed": "grabd", "carried": "ca-rid",
    "touched": "tacht", "scratched": "skracht", "threw": "zru",
    "tossed": "tost", "shook": "shuk", "pinched": "pincht", "slapped": "slapt",
    "woke up": "uouk ap", "burned": "bernd", "tied": "taid", "helped": "jelpt",
    "saved": "seivd", "protected": "pro-tec-tid", "scared": "skerd",
    "surprised": "ser-praizd", "bothered": "ba-derd", "distracted": "dis-trac-tid",
    "deceived": "di-sivd", "convinced": "con-vinst", "forced": "forst",
    "stopped": "stopt", "allowed": "a-laud", "injured": "in-yurd",
    "healed": "jild", "confused": "con-fiuzd", "gave": "gueiv",
    "brought": "brot", "bought": "bot", "sold": "sould", "delivered": "di-li-verd",
    "stole": "stoul", "took": "tuk", "offered": "o-ferd", "showed": "shoud",
    "paid": "peid", "lent": "lent", "returned": "ri-ternd",
    "threw away": "zru e-uei", "loved": "lavd", "hated": "jei-tid",
    "missed": "mist", "needed": "ni-did", "wanted": "uan-tid",
    "preferred": "pri-ferd", "trusted": "tras-tid", "respected": "res-pec-tid",
    "waited": "uei-tid", "forgot": "for-gat", "rejected": "ri-yec-tid",
    "accepted": "ac-sep-tid", "hired": "ja-ierd", "fired": "fa-ierd",
}

# If the spreadsheet is missing, the game still runs on this tiny seed list.
_FALLBACK_LEVEL1_VERBS = [
    {"id": "golpear", "gloss": "hit",
     "conj": {"yo": "golpeé", "tu": "golpeaste", "nosotros": "golpeamos",
              "ellos": "golpearon", "3rd_singular": "golpeó"},
     "dative": False, "hint_image": "/static/images/phantom_pronouns/golpear.webp"},
    {"id": "ayudar", "gloss": "helped",
     "conj": {"yo": "ayudé", "tu": "ayudaste", "nosotros": "ayudamos",
              "ellos": "ayudaron", "3rd_singular": "ayudó"},
     "dative": False, "hint_image": "/static/images/phantom_pronouns/ayudar.webp"},
]

_FALLBACK_SUBJECT_OBJECT_CLITICS = {
    sid: {
        "me": [] if sid in ("i", "we") else ["me"],
        "us": [] if sid in ("i", "we") else ["nos"],
        "you": ["te", "lo", "la"] if sid != "you" else [],
        "them": ["los", "las"],
        "him": ["lo"],
        "her": ["la"],
        "it": ["lo", "la"],
    }
    for sid in ("i", "we", "you", "they", "he", "she", "it")
}


def _strip_accents(text):
    return (text.replace("á", "a").replace("é", "e").replace("í", "i")
                .replace("ó", "o").replace("ú", "u"))


def _slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def feliponetica_for(gloss):
    key = gloss.strip().lower()
    if key in _PHONETIC_OVERRIDES:
        return f"[ {_PHONETIC_OVERRIDES[key]} ]"
    return f"[ {key} ]"


def conjugate_preterite(yo_form):
    """Given just the 1st-person-singular preterite form, derive tú,
    nosotros, ellos, and the ambiguous 3rd-person-singular form."""
    yo_form = str(yo_form).strip().lower()  # normalize — the sheet mixes cases
    key = _strip_accents(yo_form)
    if key in _IRREGULAR_PRETERITE:
        return dict(_IRREGULAR_PRETERITE[key])

    low = yo_form
    if low.endswith("qué"):
        stem, cls = yo_form[:-3] + "c", "ar"
    elif low.endswith("gué"):
        stem, cls = yo_form[:-3] + "g", "ar"
    elif low.endswith("cé"):
        stem, cls = yo_form[:-2] + "z", "ar"
    elif low.endswith(("é", "e")):  # tolerate a missing accent in source data
        stem, cls = yo_form[:-1], "ar"
    elif low.endswith(("í", "i")):
        stem, cls = yo_form[:-1], "ir"
    else:
        stem, cls = yo_form, "ar"

    if cls == "ar":
        return {
            "yo": yo_form if low.endswith("é") else stem + "é",
            "tu": stem + "aste",
            "nosotros": stem + "amos",
            "ellos": stem + "aron",
            "3rd_singular": stem + "ó",
        }
    vowel_stem = bool(stem) and stem[-1] in "aeiouáéíóú"
    return {
        "yo": yo_form if low.endswith("í") else stem + "í",
        "tu": stem + "iste",
        "nosotros": stem + "imos",
        "ellos": stem + ("yeron" if vowel_stem else "ieron"),
        "3rd_singular": stem + ("yó" if vowel_stem else "ió"),
    }


_level1_cache = None  # {"verbs": [...], "clitics": {...}} populated on first use


def _parse_level1_workbook():
    import openpyxl  # imported lazily so the module still loads without it installed

    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))

    # --- subject/object clitic compatibility table ---
    subject_row_map = {"i": "i", "we": "we", "you (*singular)": "you",
                        "they": "they", "he": "he", "she": "she", "it": "it"}
    object_columns = {
        "me": [1], "us": [2], "you": [3, 4, 5, 6, 7, 8, 9],
        "them": [10, 11, 12], "him": [13, 14], "her": [15, 16], "it": [17, 18, 19],
    }
    clitics = {}
    header_row_idx = next(
        i for i, r in enumerate(rows) if r and r[0] == "Subject Pronoun"
    )
    for r in rows[header_row_idx + 1: header_row_idx + 20]:
        if not r or not r[0]:
            continue
        label = str(r[0]).strip().lower()
        if label not in subject_row_map:
            continue
        sid = subject_row_map[label]
        clitics[sid] = {}
        for obj_id, cols in object_columns.items():
            values = []
            for c in cols:
                v = r[c] if c < len(r) else None
                if v and v not in values:
                    values.append(v)
            clitics[sid][obj_id] = values

    # --- verb table ---
    verb_header_idx = next(
        i for i, r in enumerate(rows) if r and r[0] == "verb in past tense"
    )
    verbs = []
    for r in rows[verb_header_idx + 1:]:
        if not r or not r[0]:
            break
        gloss, yo_form = str(r[0]).strip(), r[1]
        if not yo_form:
            continue
        dative = any(cell in ("X", "as indirect object") for cell in r)
        conj = conjugate_preterite(str(yo_form))
        verbs.append({
            "id": _slugify(gloss) or f"verb_{len(verbs)}",
            "gloss": gloss.lower(),
            "conj": conj,
            "dative": dative,
            "hint_image": f"/static/images/phantom_pronouns/verbs/{_slugify(gloss)}.webp",
        })

    return {"verbs": verbs, "clitics": clitics}


def _get_level1_data():
    global _level1_cache
    if _level1_cache is None:
        try:
            _level1_cache = _parse_level1_workbook()
            if not _level1_cache["verbs"] or not _level1_cache["clitics"]:
                raise ValueError("Workbook parsed but produced no data")
        except Exception:
            _level1_cache = {
                "verbs": _FALLBACK_LEVEL1_VERBS,
                "clitics": _FALLBACK_SUBJECT_OBJECT_CLITICS,
            }
    return _level1_cache


# ============================================================
# EXERCISE GENERATION
# ============================================================

def _capitalize(word):
    return word[:1].upper() + word[1:] if word else word


def _build_level1_exercise():
    data = _get_level1_data()
    verb = random.choice(data["verbs"])
    clitics = data["clitics"]

    # Only offer subjects for which at least one object is grammatical.
    candidate_subjects = [
        sid for sid in SUBJECTS_BY_ID
        if any(clitics.get(sid, {}).get(obj_id) for obj_id in DIRECT_OBJECT_WORDS_BY_ID)
    ] or list(SUBJECTS_BY_ID)
    subject_id = random.choice(candidate_subjects)
    subject = SUBJECTS_BY_ID[subject_id]

    valid_objects = [
        obj_id for obj_id in DIRECT_OBJECT_WORDS_BY_ID
        if clitics.get(subject_id, {}).get(obj_id)
    ] or list(DIRECT_OBJECT_WORDS_BY_ID)
    object_id = random.choice(valid_objects)
    object_word = DIRECT_OBJECT_WORDS_BY_ID[object_id]

    candidate_clitics = clitics.get(subject_id, {}).get(object_id) or ["lo"]
    if verb["dative"] and object_id in ("him", "her", "them", "it"):
        dative_only = [c for c in candidate_clitics if c.startswith("le")]
        candidate_clitics = dative_only or candidate_clitics
    object_es = random.choice(candidate_clitics)

    conj_group = subject["conj_group"]
    conjugated = verb["conj"][conj_group]

    context_line = None
    if conj_group == "3rd_singular":
        context_line = random.choice(CONTEXT_NOUNS[subject["gender"]])

    target_clause = f"{_capitalize(object_es)} {conjugated}."
    spanish_prompt = f"{context_line} {target_clause}" if context_line else target_clause
    english_sentence = f"{_capitalize(subject['en'])} {verb['gloss']} {object_word['en']}."

    return {
        "spanish_prompt": spanish_prompt,
        "verb_infinitive": verb["gloss"],
        "verb_phonetic": feliponetica_for(verb["gloss"]),
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
    return _build_other_level_exercise(level_id)


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
