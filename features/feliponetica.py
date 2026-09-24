"""Private server-side Feliponetica conversion feature."""
import os
import re

import nltk
from flask import Blueprint, redirect, render_template, request, session, url_for
from g2p_en import G2p

feliponetica_bp = Blueprint("feliponetica", __name__)

NLTK_DATA_PATH = os.environ.get("NLTK_DATA_PATH", "/opt/render/nltk_data")
if NLTK_DATA_PATH not in nltk.data.path:
    nltk.data.path.insert(0, NLTK_DATA_PATH)

for _nltk_package in ("averaged_perceptron_tagger_eng", "cmudict"):
    nltk.download(_nltk_package, download_dir=NLTK_DATA_PATH, quiet=True)

# Keep the converter and its pronunciation rules on the server.  Templates and
# browser JavaScript receive only the requested result, never these mappings.
CMU_TO_FELIPONETICA = {
    "AA":"a˂", "AE":"aʰ", "AH":"uʰ", "AO":"a˂", "AW":"au", "AY":"ai",
    "EH":"e", "ER":"r", "EY":"ei", "IH":"iʰ", "IY":"i", "OW":"ou",
    "OY":"oi", "UH":"u", "UW":"uu", "P":"p", "B":"b", "T":"t",
    "D":"d", "K":"k", "G":"g", "F":"f", "V":"v", "TH":"thˢ",
    "DH":"thᶻ", "S":"s", "Z":"z", "SH":"sh", "ZH":"shᶻ", "HH":"j",
    "CH":"ch", "JH":"shᶻ", "M":"m", "N":"n", "NG":"ng", "L":"l",
    "R":"r", "W":"w", "Y":"ll", "DW":"du",
}
CMU_TO_FELIPONETICA_POLLITO = {
    "AA":"a", "AE":"a", "AH":"a", "AO":"a", "AW":"au", "AY":"ai",
    "EH":"e", "ER":"r", "EY":"ei", "IH":"i", "IY":"ii", "OW":"ou",
    "OY":"oi", "UH":"u", "UW":"uu", "P":"p", "B":"b", "T":"t",
    "D":"d", "K":"k", "G":"g", "F":"f", "V":"v", "TH":"t", "DH":"d",
    "S":"s", "Z":"z", "SH":"sh", "ZH":"(shᶻ)", "HH":"j", "CH":"ch",
    "JH":"ch", "M":"m", "N":"n", "NG":"ng", "L":"l", "R":"r", "W":"w", "Y":"ll",
}
_g2p = None
_PHONEME_PATTERN = re.compile(r"^[A-Z]+[0-2]?$")
_VOWEL_PHONEMES = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}
_VALID_ONSETS = {
    "B", "CH", "D", "DH", "F", "G", "HH", "JH", "K", "L", "M", "N", "P", "R", "S", "SH", "T", "TH", "V", "W", "Y", "Z",
    "BL", "BR", "CL", "CR", "DR", "DW", "FL", "FR", "GL", "GR", "KL", "KR", "PL", "PR", "SK", "SL", "SM", "SN", "SP", "ST", "SW", "THR", "TR", "TW", "SHR", "CHW",
    "SCR", "SHR", "SKR", "SPL", "SPR", "SQU", "STR",
}

def _converter():
    global _g2p
    if _g2p is None:
        _g2p = G2p()
    return _g2p

def _syllable_starts(phonemes):
    """Return phoneme positions that begin a new syllable in each word."""
    starts = set()
    word_start = 0

    def mark_word(word_end):
        phone_indexes = [index for index in range(word_start, word_end) if _PHONEME_PATTERN.match(phonemes[index])]
        vowel_indexes = [index for index in phone_indexes if re.sub(r"\d", "", phonemes[index]) in _VOWEL_PHONEMES]
        for previous_vowel, next_vowel in zip(vowel_indexes, vowel_indexes[1:]):
            between = [re.sub(r"\d", "", phonemes[index]) for index in phone_indexes if previous_vowel < index < next_vowel]
            onset_length = 0
            for length in range(min(3, len(between)), 0, -1):
                if "".join(between[-length:]) in _VALID_ONSETS:
                    onset_length = length
                    break
            starts.add(next_vowel - onset_length)

    for index, phone in enumerate(phonemes):
        if phone == " " or not _PHONEME_PATTERN.match(phone):
            mark_word(index)
            word_start = index + 1
    mark_word(len(phonemes))
    return starts

def convert_to_feliponetica(text, phoneme_map=CMU_TO_FELIPONETICA):
    phonemes = _converter()(text)
    syllable_starts = _syllable_starts(phonemes)
    for index, phone in enumerate(phonemes):
        if re.sub(r"\d", "", phone) == "DH":
            previous = [re.sub(r"\d", "", phonemes[position]) for position in (index - 2, index - 1) if position >= 0]
            if previous == ["W", "IH"]:
                phonemes[index] = "TH"

    converted, index = [], 0
    while index < len(phonemes):
        if index in syllable_starts:
            converted.append("-")
        phone = phonemes[index]
        if phone == " ":
            converted.append(" "); index += 1; continue
        if not _PHONEME_PATTERN.match(phone):
            converted.append(phone); index += 1; continue
        phone = re.sub(r"\d", "", phone)
        next_phone = re.sub(r"\d", "", phonemes[index + 1]) if index + 1 < len(phonemes) else ""
        after_next = re.sub(r"\d", "", phonemes[index + 2]) if index + 2 < len(phonemes) else ""
        after_after = re.sub(r"\d", "", phonemes[index + 3]) if index + 3 < len(phonemes) else ""
        if phone == "Y" and next_phone == "UW" and after_next == "AH" and after_after == "L":
            converted.append("iuol"); index += 4; continue
        if phone == "Y" and next_phone == "UW" and after_next == "L":
            converted.append("iuol"); index += 3; continue
        if phone == "Y" and next_phone == "UW":
            converted.append("iu"); index += 2; continue
        if phone == "AO" and next_phone == "R":
            converted.append("or"); index += 2; continue
        if phone == "NG" and next_phone == "K":
            converted.append("nk"); index += 2; continue
        if phone in {"UW", "IY", "EY", "AY", "OY"} and next_phone == "L":
            converted.append(phoneme_map.get(phone, phone) + "ol"); index += 2; continue
        converted.append(phoneme_map.get(phone, phone))
        index += 1
    return "".join(converted)

def convert_to_feliponetica_pollito(text):
    return convert_to_feliponetica(text, CMU_TO_FELIPONETICA_POLLITO)

def _require_login():
    if "username" not in session or "role" not in session:
        return redirect(url_for("login"))
    return None

def _require_admin():
    access_error = _require_login()
    if access_error:
        return access_error
    if session.get("role") != "admin":
        return {"error": "Admin access required"}, 403
    return None

def _transcribe_payload(require_admin=False):
    access_error = _require_admin() if require_admin else _require_login()
    if access_error:
        return None, access_error
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    dialect = str(payload.get("dialect", "pollito")).lower()
    if not text:
        return None, ({"error": "text is required"}, 400)
    if dialect not in {"pollito", "gallo"}:
        return None, ({"error": "dialect must be pollito or gallo"}, 400)
    converter = convert_to_feliponetica_pollito if dialect == "pollito" else convert_to_feliponetica
    return {"dialect": dialect, "text": text, "result": converter(text)}, None

@feliponetica_bp.route("/feliponetica-ingles", methods=["GET", "POST"])
@feliponetica_bp.route("/feliponetica_ingles", methods=["GET", "POST"])
def feliponetica_ingles():
    access_error = _require_login()
    if access_error:
        return access_error
    pollito_result = gallo_result = None
    pollito_input = gallo_input = ""
    if request.method == "POST":
        dialect = request.form.get("dialect", "pollito")
        text = request.form.get("transcript_text", "").strip()
        if dialect == "gallo":
            gallo_input, gallo_result = text, convert_to_feliponetica(text) if text else None
        else:
            pollito_input, pollito_result = text, convert_to_feliponetica_pollito(text) if text else None
    return render_template("feliponetica_ingles.html", pollito_result=pollito_result, gallo_result=gallo_result, pollito_input=pollito_input, gallo_input=gallo_input)

@feliponetica_bp.post("/api/feliponetica/transcribe")
def feliponetica_transcribe_api():
    result, error = _transcribe_payload(require_admin=True)
    return error or result

@feliponetica_bp.post("/api/feliponetica/transcribe-page")
def feliponetica_transcribe_page():
    result, error = _transcribe_payload()
    return error or result
