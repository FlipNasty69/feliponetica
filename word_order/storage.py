import os
import sqlite3

from flask import current_app


SCHEMA = """
CREATE TABLE IF NOT EXISTS levels (
    level_id INTEGER PRIMARY KEY,
    level_name_en TEXT NOT NULL,
    level_name_es TEXT NOT NULL,
    cefr TEXT,
    grammar_focus TEXT,
    unlocked_structures TEXT,
    target_tokens TEXT,
    notes_es TEXT
);
CREATE TABLE IF NOT EXISTS words (
    word_id TEXT PRIMARY KEY,
    english TEXT NOT NULL,
    spanish TEXT NOT NULL,
    pos TEXT NOT NULL,
    subtype TEXT,
    countability TEXT,
    animacy TEXT,
    verb_class TEXT,
    cefr TEXT,
    level_min INTEGER,
    tags TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (level_min) REFERENCES levels(level_id) ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS verb_forms (
    base TEXT PRIMARY KEY,
    third_person TEXT,
    past TEXT,
    past_participle TEXT,
    ing TEXT,
    spanish TEXT,
    verb_class TEXT,
    allows_iobj TEXT,
    complement_type TEXT,
    irregular TEXT,
    level_min INTEGER,
    FOREIGN KEY (level_min) REFERENCES levels(level_id) ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS patterns (
    pattern_id TEXT PRIMARY KEY,
    domain TEXT,
    family TEXT,
    pattern_name TEXT NOT NULL,
    template TEXT,
    spanish_guide TEXT,
    min_level INTEGER NOT NULL,
    max_tokens INTEGER,
    recursive TEXT,
    example_en TEXT,
    FOREIGN KEY (min_level) REFERENCES levels(level_id) ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS pattern_slots (
    pattern_id TEXT NOT NULL,
    slot_order INTEGER NOT NULL,
    slot_code TEXT NOT NULL,
    required TEXT,
    allowed_pos TEXT,
    allowed_subtype TEXT,
    agreement_rule TEXT,
    notes_es TEXT,
    PRIMARY KEY (pattern_id, slot_order),
    FOREIGN KEY (pattern_id) REFERENCES patterns(pattern_id) ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS challenges (
    challenge_id TEXT PRIMARY KEY,
    level_id INTEGER NOT NULL,
    pattern_id TEXT NOT NULL,
    prompt_es TEXT NOT NULL,
    correct_en TEXT NOT NULL,
    shuffled_tokens TEXT NOT NULL,
    accept_alt_en TEXT,
    explanation_es TEXT,
    skill_tag TEXT,
    difficulty TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    source_type TEXT,
    token_count INTEGER,
    FOREIGN KEY (level_id) REFERENCES levels(level_id) ON UPDATE CASCADE,
    FOREIGN KEY (pattern_id) REFERENCES patterns(pattern_id) ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS words_lookup_idx ON words(pos, subtype, level_min, active);
CREATE INDEX IF NOT EXISTS words_cefr_idx ON words(cefr);
CREATE INDEX IF NOT EXISTS verb_forms_lookup_idx ON verb_forms(verb_class, level_min);
CREATE INDEX IF NOT EXISTS patterns_lookup_idx ON patterns(min_level, domain, family);
CREATE INDEX IF NOT EXISTS challenges_level_active_idx ON challenges(level_id, active, difficulty);
CREATE INDEX IF NOT EXISTS challenges_pattern_idx ON challenges(pattern_id);
CREATE INDEX IF NOT EXISTS challenges_skill_tag_idx ON challenges(skill_tag);
CREATE TABLE IF NOT EXISTS word_order_source_state (
    source_path TEXT PRIMARY KEY,
    modified_ns INTEGER NOT NULL,
    file_size INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS word_order_sessions (
    session_id TEXT PRIMARY KEY,
    profile_key TEXT NOT NULL,
    level_id INTEGER NOT NULL,
    challenge_ids TEXT NOT NULL,
    current_index INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,
    mistakes INTEGER NOT NULL DEFAULT 0,
    checked INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (level_id) REFERENCES levels(level_id)
);
CREATE INDEX IF NOT EXISTS word_order_sessions_profile_idx
    ON word_order_sessions(profile_key, level_id, started_at);
CREATE TABLE IF NOT EXISTS word_order_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,
    submitted_answer TEXT NOT NULL,
    correct INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL,
    response_time_ms INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, challenge_id),
    FOREIGN KEY (session_id) REFERENCES word_order_sessions(session_id),
    FOREIGN KEY (challenge_id) REFERENCES challenges(challenge_id)
);
CREATE TABLE IF NOT EXISTS word_order_progress (
    profile_key TEXT NOT NULL,
    level_id INTEGER NOT NULL,
    best_score INTEGER NOT NULL DEFAULT 0,
    best_correct_count INTEGER NOT NULL DEFAULT 0,
    best_challenge_count INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    correct_attempts INTEGER NOT NULL DEFAULT 0,
    current_streak INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,
    last_played TEXT,
    completed_at TEXT,
    PRIMARY KEY(profile_key, level_id),
    FOREIGN KEY (level_id) REFERENCES levels(level_id)
);
"""


def database_path():
    configured_path = current_app.config.get("WORD_ORDER_DATABASE")
    if configured_path:
        return os.fspath(configured_path)
    os.makedirs(current_app.instance_path, exist_ok=True)
    return os.path.join(current_app.instance_path, "word_order.sqlite3")


def initialize_database(path=None):
    path = os.fspath(path or database_path())
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
    finally:
        connection.close()


def connect_database():
    path = database_path()
    initialize_database(path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection