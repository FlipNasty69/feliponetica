import json
import random
import re
import uuid
from datetime import datetime, timezone

from word_order.generator import AuthoredChallengeGenerator


PUNCTUATION_BEFORE_SPACE = re.compile(r"\s+([.,?!])")
CHALLENGE_GENERATOR = AuthoredChallengeGenerator()


class GameStateError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def split_tokens(token_string):
    if not token_string:
        return []
    return [token.strip() for token in str(token_string).split("|") if token.strip()]


def join_tokens(tokens):
    answer = " ".join(str(token).strip() for token in tokens if str(token).strip())
    return PUNCTUATION_BEFORE_SPACE.sub(r"\1", answer)


def normalize_answer(answer):
    normalized = " ".join(str(answer or "").split())
    return PUNCTUATION_BEFORE_SPACE.sub(r"\1", normalized).casefold()


def _challenge_counts(connection):
    rows = connection.execute("""
        SELECT levels.level_id, COUNT(challenges.challenge_id) AS challenge_count
        FROM levels
        LEFT JOIN challenges
            ON challenges.level_id = levels.level_id
            AND challenges.active = 1
        LEFT JOIN patterns
            ON patterns.pattern_id = challenges.pattern_id
            AND patterns.min_level <= levels.level_id
        WHERE challenges.challenge_id IS NULL OR patterns.pattern_id IS NOT NULL
        GROUP BY levels.level_id
    """).fetchall()
    return {row["level_id"]: row["challenge_count"] for row in rows}


def get_level_catalog(connection, profile_key):
    levels = connection.execute(
        "SELECT * FROM levels ORDER BY level_id"
    ).fetchall()
    counts = _challenge_counts(connection)
    progress_rows = connection.execute(
        "SELECT * FROM word_order_progress WHERE profile_key = ?",
        (profile_key,),
    ).fetchall()
    progress = {row["level_id"]: row for row in progress_rows}

    catalog = []
    for index, level in enumerate(levels):
        total = counts.get(level["level_id"], 0)
        saved = progress.get(level["level_id"])
        best_correct = saved["best_correct_count"] if saved else 0
        percentage = min(100, round(best_correct * 100 / total)) if total else 0
        unlocked = index == 0 or (
            catalog[index - 1]["challenge_count"] > 0
            and catalog[index - 1]["completion_percentage"] >= 80
        )
        completed = bool(total and percentage >= 80)
        status = "completed" if completed else "available" if unlocked else "locked"
        catalog.append({
            "id": level["level_id"],
            "name_en": level["level_name_en"],
            "name_es": level["level_name_es"],
            "cefr": level["cefr"],
            "grammar_focus": level["grammar_focus"],
            "unlocked_structures": level["unlocked_structures"],
            "notes_es": level["notes_es"],
            "challenge_count": total,
            "completion_percentage": percentage,
            "best_score": saved["best_score"] if saved else 0,
            "status": status,
        })
    return catalog


def _profile_session(connection, session_id, profile_key):
    game_session = connection.execute(
        "SELECT * FROM word_order_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not game_session or game_session["profile_key"] != profile_key:
        raise GameStateError("No encontramos esa partida.", 404)
    return game_session


def _current_challenge(connection, game_session):
    challenge_ids = json.loads(game_session["challenge_ids"])
    index = game_session["current_index"]
    if index >= len(challenge_ids):
        return None
    challenge = connection.execute("""
        SELECT challenges.*, patterns.pattern_name, patterns.spanish_guide
        FROM challenges
        JOIN patterns ON patterns.pattern_id = challenges.pattern_id
        WHERE challenges.challenge_id = ?
    """, (challenge_ids[index],)).fetchone()
    return challenge


def serialize_current_session(connection, game_session):
    challenge = _current_challenge(connection, game_session)
    if not challenge:
        return {
            "session_id": game_session["session_id"],
            "completed": True,
            "score": game_session["score"],
        }
    level = connection.execute(
        "SELECT level_name_en, level_name_es FROM levels WHERE level_id = ?",
        (game_session["level_id"],),
    ).fetchone()
    total = len(json.loads(game_session["challenge_ids"]))
    tokens = split_tokens(challenge["shuffled_tokens"])
    random.Random(f"{game_session['session_id']}:{challenge['challenge_id']}").shuffle(tokens)
    state = {
        "session_id": game_session["session_id"],
        "level_id": game_session["level_id"],
        "level_name_en": level["level_name_en"],
        "level_name_es": level["level_name_es"],
        "challenge_id": challenge["challenge_id"],
        "prompt_es": challenge["prompt_es"],
        "tokens": tokens,
        "skill_tag": challenge["skill_tag"] or "",
        "challenge_index": game_session["current_index"],
        "challenge_number": game_session["current_index"] + 1,
        "total_challenges": total,
        "score": game_session["score"],
        "streak": game_session["streak"],
        "checked": bool(game_session["checked"]),
        "completed": bool(game_session["completed_at"]),
    }
    if game_session["checked"]:
        attempt = connection.execute("""
            SELECT word_order_attempts.correct, challenges.correct_en,
                challenges.explanation_es, challenges.skill_tag, patterns.spanish_guide
            FROM word_order_attempts
            JOIN challenges ON challenges.challenge_id = word_order_attempts.challenge_id
            JOIN patterns ON patterns.pattern_id = challenges.pattern_id
            WHERE word_order_attempts.session_id = ? AND challenges.challenge_id = ?
        """, (game_session["session_id"], challenge["challenge_id"])).fetchone()
        if attempt:
            state["feedback"] = {
                "correct": bool(attempt["correct"]),
                "correct_answer": attempt["correct_en"],
                "explanation_es": attempt["explanation_es"] or attempt["spanish_guide"] or "",
                "skill_tag": attempt["skill_tag"] or "",
                "score_change": 10 if attempt["correct"] else 0,
                "streak": game_session["streak"],
                "next_available": game_session["current_index"] + 1 < total,
            }
    return state


def start_session(connection, profile_key, level_id):
    try:
        level_id = int(level_id)
    except (TypeError, ValueError) as error:
        raise GameStateError("El nivel no es válido.") from error

    catalog = get_level_catalog(connection, profile_key)
    level = next((item for item in catalog if item["id"] == level_id), None)
    if not level:
        raise GameStateError("No encontramos ese nivel.", 404)
    if level["status"] == "locked":
        raise GameStateError("Completa el nivel anterior para continuar.", 403)

    challenge_ids = CHALLENGE_GENERATOR.challenge_ids(connection, level_id)
    if not challenge_ids:
        raise GameStateError("Este nivel todavía no tiene desafíos activos.", 404)

    random.shuffle(challenge_ids)
    previous = connection.execute("""
        SELECT challenge_ids FROM word_order_sessions
        WHERE profile_key = ? AND level_id = ? AND completed_at IS NOT NULL
        ORDER BY started_at DESC LIMIT 1
    """, (profile_key, level_id)).fetchone()
    if previous and len(challenge_ids) > 1:
        previous_ids = json.loads(previous["challenge_ids"])
        if challenge_ids[0] == previous_ids[0]:
            challenge_ids[0], challenge_ids[1] = challenge_ids[1], challenge_ids[0]

    now = utc_now()
    session_id = uuid.uuid4().hex
    connection.execute("""
        INSERT INTO word_order_sessions
            (session_id, profile_key, level_id, challenge_ids, started_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, profile_key, level_id, json.dumps(challenge_ids), now, now))
    game_session = connection.execute(
        "SELECT * FROM word_order_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    return serialize_current_session(connection, game_session)


def resume_session(connection, session_id, profile_key):
    game_session = _profile_session(connection, session_id, profile_key)
    if game_session["completed_at"]:
        raise GameStateError("Esta partida ya terminó.", 409)
    return serialize_current_session(connection, game_session)


def submit_answer(connection, session_id, profile_key, answer, response_time_ms=None):
    game_session = _profile_session(connection, session_id, profile_key)
    if game_session["completed_at"]:
        raise GameStateError("Esta partida ya terminó.", 409)
    if game_session["checked"]:
        raise GameStateError("Esta respuesta ya fue revisada.", 409)

    challenge = _current_challenge(connection, game_session)
    if not challenge or not challenge["active"]:
        raise GameStateError("Este desafío ya no está disponible.", 409)
    submitted = str(answer or "")
    accepted_answers = [challenge["correct_en"]]
    accepted_answers.extend(
        alternative.strip()
        for alternative in (challenge["accept_alt_en"] or "").split("||")
        if alternative.strip()
    )
    accepted_normalized = {normalize_answer(item) for item in accepted_answers}
    is_correct = normalize_answer(submitted) in accepted_normalized
    attempt_number = 1
    response_time_ms = max(0, min(int(response_time_ms or 0), 600000))
    now = utc_now()
    streak = game_session["streak"] + 1 if is_correct else 0
    best_streak = max(game_session["best_streak"], streak)
    score_change = 10 if is_correct else 0

    connection.execute("""
        INSERT INTO word_order_attempts
            (session_id, challenge_id, submitted_answer, correct, attempt_number,
             response_time_ms, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, challenge["challenge_id"], submitted, int(is_correct),
        attempt_number, response_time_ms, now,
    ))
    connection.execute("""
        UPDATE word_order_sessions SET
            checked = 1,
            score = score + ?,
            correct_count = correct_count + ?,
            streak = ?,
            best_streak = ?,
            mistakes = mistakes + ?,
            updated_at = ?
        WHERE session_id = ?
    """, (
        score_change, int(is_correct), streak, best_streak,
        int(not is_correct), now, session_id,
    ))
    connection.execute("""
        INSERT INTO word_order_progress
            (profile_key, level_id, attempt_count, correct_attempts, current_streak,
             best_streak, last_played)
        VALUES (?, ?, 1, ?, ?, ?, ?)
        ON CONFLICT(profile_key, level_id) DO UPDATE SET
            attempt_count = word_order_progress.attempt_count + 1,
            correct_attempts = word_order_progress.correct_attempts + excluded.correct_attempts,
            current_streak = excluded.current_streak,
            best_streak = MAX(word_order_progress.best_streak, excluded.best_streak),
            last_played = excluded.last_played
    """, (
        profile_key, game_session["level_id"], int(is_correct), streak, best_streak, now,
    ))
    explanation = challenge["explanation_es"] or challenge["spanish_guide"] or ""
    total = len(json.loads(game_session["challenge_ids"]))
    return {
        "correct": is_correct,
        "correct_answer": challenge["correct_en"],
        "explanation_es": explanation,
        "skill_tag": challenge["skill_tag"] or "",
        "score_change": score_change,
        "streak": streak,
        "next_available": game_session["current_index"] + 1 < total,
    }


def continue_session(connection, session_id, profile_key):
    game_session = _profile_session(connection, session_id, profile_key)
    if game_session["completed_at"]:
        raise GameStateError("Esta partida ya terminó.", 409)
    if not game_session["checked"]:
        raise GameStateError("Revisa tu respuesta antes de continuar.", 409)

    challenge_ids = json.loads(game_session["challenge_ids"])
    now = utc_now()
    next_index = game_session["current_index"] + 1
    if next_index < len(challenge_ids):
        connection.execute("""
            UPDATE word_order_sessions SET current_index = ?, checked = 0, updated_at = ?
            WHERE session_id = ?
        """, (next_index, now, session_id))
        updated = connection.execute(
            "SELECT * FROM word_order_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return {"completed": False, "challenge": serialize_current_session(connection, updated)}

    connection.execute(
        "UPDATE word_order_sessions SET completed_at = ?, updated_at = ? WHERE session_id = ?",
        (now, now, session_id),
    )
    total = len(challenge_ids)
    progress = connection.execute("""
        SELECT best_correct_count, best_score, completed_at FROM word_order_progress
        WHERE profile_key = ? AND level_id = ?
    """, (profile_key, game_session["level_id"])).fetchone()
    best_correct = max(progress["best_correct_count"], game_session["correct_count"]) if progress else game_session["correct_count"]
    best_score = max(progress["best_score"], game_session["score"]) if progress else game_session["score"]
    completed_at = (progress["completed_at"] if progress else None)
    if total and best_correct / total >= 0.8:
        completed_at = completed_at or now
    connection.execute("""
        INSERT INTO word_order_progress
            (profile_key, level_id, best_score, best_correct_count,
             best_challenge_count, last_played, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(profile_key, level_id) DO UPDATE SET
            best_score = MAX(word_order_progress.best_score, excluded.best_score),
            best_correct_count = MAX(word_order_progress.best_correct_count, excluded.best_correct_count),
            best_challenge_count = excluded.best_challenge_count,
            last_played = excluded.last_played,
            completed_at = COALESCE(word_order_progress.completed_at, excluded.completed_at)
    """, (
        profile_key, game_session["level_id"], best_score, best_correct,
        total, now, completed_at,
    ))
    return {"completed": True, "result_url": f"/games/word-order/result/{session_id}"}


def get_result(connection, session_id, profile_key):
    game_session = _profile_session(connection, session_id, profile_key)
    if not game_session["completed_at"]:
        raise GameStateError("Esta partida todavía no terminó.", 409)
    total = len(json.loads(game_session["challenge_ids"]))
    level = connection.execute(
        "SELECT level_name_en, level_name_es FROM levels WHERE level_id = ?",
        (game_session["level_id"],),
    ).fetchone()
    percentage = round(game_session["correct_count"] * 100 / total) if total else 0
    return {
        "session_id": session_id,
        "level_id": game_session["level_id"],
        "level_name_en": level["level_name_en"],
        "level_name_es": level["level_name_es"],
        "score": game_session["score"],
        "correct_count": game_session["correct_count"],
        "challenge_count": total,
        "completion_percentage": percentage,
        "best_streak": game_session["best_streak"],
        "mistakes": game_session["mistakes"],
    }