import uuid

from flask import abort, current_app, jsonify, redirect, render_template, request, session, url_for

from word_order import word_order_bp
from word_order.gameplay import (
    GameStateError,
    continue_session,
    get_level_catalog,
    get_result,
    resume_session,
    start_session,
    submit_answer,
)
from word_order.storage import connect_database


def _profile_key():
    user_id = session.get("user_id")
    if user_id is not None:
        return f"user:{user_id}"
    if "word_order_guest_id" not in session:
        session["word_order_guest_id"] = uuid.uuid4().hex
    return f"guest:{session['word_order_guest_id']}"


def _json_game_call(operation, *args):
    connection = connect_database()
    try:
        with connection:
            result = operation(connection, *args)
        return jsonify(result)
    except GameStateError as error:
        return jsonify({"error": str(error)}), error.status_code
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    finally:
        connection.close()


@word_order_bp.route("/")
def index():
    return redirect(url_for("word_order.levels_page"))


@word_order_bp.route("/levels")
def levels_page():
    return render_template("word_order/levels.html")


@word_order_bp.route("/level/<int:level_id>")
def level_detail(level_id):
    return redirect(url_for("word_order.play_level", level_id=level_id))


@word_order_bp.route("/play/<int:level_id>")
def play_level(level_id):
    return render_template("word_order/play.html", level_id=level_id)


@word_order_bp.route("/api/levels")
def levels_api():
    connection = connect_database()
    try:
        return jsonify(get_level_catalog(connection, _profile_key()))
    finally:
        connection.close()


@word_order_bp.route("/api/session", methods=["POST"])
def create_game_session():
    payload = request.get_json(silent=True) or {}
    return _json_game_call(start_session, _profile_key(), payload.get("level_id"))


@word_order_bp.route("/api/session/<session_id>")
def resume_game_session(session_id):
    return _json_game_call(resume_session, session_id, _profile_key())


@word_order_bp.route("/check", methods=["POST"])
def check_answer():
    payload = request.get_json(silent=True) or {}
    if not payload.get("session_id"):
        return jsonify({"error": "session_id is required"}), 400
    return _json_game_call(
        submit_answer,
        payload["session_id"],
        _profile_key(),
        payload.get("answer", ""),
        payload.get("response_time_ms"),
    )


@word_order_bp.route("/api/continue", methods=["POST"])
def continue_game_session():
    payload = request.get_json(silent=True) or {}
    if not payload.get("session_id"):
        return jsonify({"error": "session_id is required"}), 400
    return _json_game_call(continue_session, payload["session_id"], _profile_key())


@word_order_bp.route("/result/<session_id>")
def result_page(session_id):
    connection = connect_database()
    try:
        result = get_result(connection, session_id, _profile_key())
    except GameStateError as error:
        if error.status_code == 409:
            return redirect(url_for("word_order.levels_page"))
        abort(error.status_code, description=str(error))
    finally:
        connection.close()
    return render_template("word_order/result.html", result=result)