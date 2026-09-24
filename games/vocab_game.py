from flask import Blueprint, render_template, jsonify, request, session
import os

# 1. Define the Blueprint instead of Flask(__name__)
# URL prefix means all routes here will automatically start with /vocab
vocab_bp = Blueprint('vocab_game', __name__, url_prefix='/vocab')

# Back-end vocabulary database containing word data, images, audios, and Feliponetica transcriptions
VOCAB_DATABASE = {
    "set_1": {
        "id": "set_1",
        "title": "subject pronouns",
        "words": [
            {
                "id": 1,
                "english": "I",
                "spanish": "yo",
                "phonetic": "ai",
                "image": "/static/images/vocab_game/I.webp",
                "audio": "/static/audio/vocab_game/I.mp3"
            },
            {
                "id": 2,
                "english": "we",
                "spanish": "nosotros",
                "phonetic": "[ wi ]",
                "image": "/static/images/vocab_game/we.webp",
                "audio": "/static/audio/vocab_game/we.mp3"
            },
            {
                "id": 3,
                "english": "you",
                "spanish": "tu",
                "phonetic": "[ llu ]",
                "image": "/static/images/vocab_game/you.webp",
                "audio": "/static/audio/vocab_game/you.mp3"
            },
            {
                "id": 4,
                "english": "they",
                "spanish": "ellos",
                "phonetic": "[ dei ]",
                "image": "/static/images/vocab_game/they.webp",
                "audio": "/static/audio/vocab_game/they.mp3"
            },
            {
                "id": 5,
                "english": "he",
                "spanish": "él",
                "phonetic": "[ ji ]",
                "image": "/static/images/vocab_game/he.webp",
                "audio": "/static/audio/vocab_game/he.mp3"
            },
            {
                "id": 6,
                "english": "she",
                "spanish": "ella",
                "phonetic": "shi",
                "image": "/static/images/vocab_game/she.webp",
                "audio": "/static/audio/vocab_game/she.mp3"
            },
            {
                "id": 7,
                "english": "it",
                "spanish": "",
                "phonetic": "it",
                "image": "/static/images/vocab_game/it.webp",
                "audio": "/static/audio/vocab_game/it.mp3"
            }                                                 
        ]
    },
    "set_2": {
        "id": "set_2",
        "title": "object pronouns",
        "words": [
            {
                "id": 3,
                "english": "you",
                "spanish": "correr",
                "phonetic": "[ rʌn ]",
                "image": "/static/images/run.jpg",
                "audio": "/static/audio/run.mp3"
            }
        ]
    }
}


# --- PAGE ROUTE ---
# Accessible at: yourdomain.com/vocab/game
@vocab_bp.route('/game')
def game_page():
    """Renders the single-page HTML game container."""
    return render_template('games/vocab_game.html')

# --- API ENDPOINTS ---
# Accessible at: yourdomain.com/vocab/api/get-vocab-sets
@vocab_bp.route('/api/get-vocab-sets', methods=['GET'])
def get_vocab_sets():
    """Returns a list of available sets for the main menu screen."""
    sets_list = [
        {"id": key, "title": val["title"]} 
        for key, val in VOCAB_DATABASE.items()
    ]
    return jsonify(sets_list)

@vocab_bp.route('/api/get-set-details', methods=['GET'])
def get_set_details():
    """Fetches items for a selected vocabulary set and initializes session state."""
    set_id = request.args.get('id')
    if set_id not in VOCAB_DATABASE:
        return jsonify({"error": "Set not found"}), 404

    selected_set = VOCAB_DATABASE[set_id]
    
    # Store active game state on server
    session['active_set_id'] = set_id
    session['current_round'] = 1
    session['word_index'] = 0

    return jsonify(selected_set["words"])

@vocab_bp.route('/api/verify-voice', methods=['POST'])
def verify_voice():
    """
    Receives recorded voice audio blob from the client.
    Validates presence of audio input without restricting progression.
    """
    if 'audio' not in request.files:
        return jsonify({"received": False, "message": "No audio file uploaded."}), 400

    audio_file = request.files['audio']
    
    # Save temporary audio file for server-side processing if needed
    temp_dir = "temp_audio"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, "user_attempt.wav")
    audio_file.save(temp_path)

    # Simple cleanup after verification
    if os.path.exists(temp_path):
        os.remove(temp_path)

    return jsonify({"received": True, "status": "Audio processed successfully."})

@vocab_bp.route('/api/reset-game', methods=['POST'])
def reset_game():
    """Clears active game session variables when returning to menu."""
    session.pop('active_set_id', None)
    session.pop('current_round', None)
    session.pop('word_index', None)
    return jsonify({"status": "reset_successful"})