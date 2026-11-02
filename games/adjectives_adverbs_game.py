import os
import re

from flask import Blueprint, current_app, render_template
from openpyxl import load_workbook


adjectives_adverbs_game_bp = Blueprint(
    "adjectives_adverbs_game",
    __name__,
    url_prefix="/adjectives-game",
)

WORKBOOK_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "..",
    "static",
    "data",
    "adjectives_adverbs_game.xlsx",
))
ADJECTIVE_POSITIONS = ("top_left", "top_right", "bottom_left", "bottom_right")


def _text(value):
    return str(value).strip() if value is not None else ""


def _adjective_id(value):
    text = _text(value)
    if text.isdigit():
        return text.zfill(5)
    return text


def _slug(value):
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "adjectives"


def _read_table(sheet, required_headers):
    rows = sheet.iter_rows(values_only=True)
    headers = next(rows, ())
    missing = required_headers.difference(headers)
    if missing:
        raise ValueError(
            f"Adjectives game workbook has an invalid {sheet.title} sheet; "
            f"missing columns: {', '.join(sorted(missing))}."
        )
    return (
        dict(zip(headers, row))
        for row in rows
        if any(value is not None for value in row)
    )


def _load_game_data(workbook_path):
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        required_sheets = {"sets", "image_audio"}
        missing_sheets = required_sheets.difference(workbook.sheetnames)
        if missing_sheets:
            raise ValueError(
                "Adjectives game workbook is missing sheets: "
                f"{', '.join(sorted(missing_sheets))}."
            )

        adjective_rows = _read_table(
            workbook["sets"],
            {
                "adjective_type",
                "group_within_type",
                "exercise_id",
                "adjective_id",
                "adjective",
                "audio_URL",
            },
        )
        image_rows = _read_table(
            workbook["image_audio"],
            {
                "adjective_type",
                "exercise_id",
                "noun",
                "adjectives_game_image_URL",
                "adjectives_game_noun_audio_URL",
                *ADJECTIVE_POSITIONS,
            },
        )

        groups = {}
        type_labels = {}
        current_type = ""
        for row in adjective_rows:
            if _text(row["adjective_type"]):
                current_type = _text(row["adjective_type"])
            adjective = _text(row["adjective"])
            adjective_id = _adjective_id(row["adjective_id"])
            if not adjective and not adjective_id:
                continue
            if not current_type or not adjective or not adjective_id:
                raise ValueError(
                    "Adjectives game workbook has an incomplete adjective row."
                )

            type_key = _slug(current_type)
            type_labels.setdefault(type_key, current_type)
            group_id = _text(row["group_within_type"])
            exercise_id = _text(row["exercise_id"])
            if not group_id or not exercise_id or not _text(row["audio_URL"]):
                raise ValueError(
                    f"Adjective {adjective!r} is missing its group, exercise, "
                    "or audio URL."
                )

            group_key = (type_key, group_id)
            group = groups.setdefault(
                group_key,
                {
                    "id": group_id,
                    "exercise_id": exercise_id,
                    "adjectives": [],
                    "exercises": [],
                },
            )
            if group["exercise_id"] != exercise_id:
                raise ValueError(
                    f"Group {group_id} for {current_type} has inconsistent "
                    "exercise IDs."
                )
            if any(item["id"] == adjective_id for item in group["adjectives"]):
                raise ValueError(
                    f"Duplicate adjective ID {adjective_id} in {current_type}."
                )
            group["adjectives"].append({
                "id": adjective_id,
                "word": adjective,
                "audio_url": _text(row["audio_URL"]),
            })

        groups_by_type_and_exercise = {}
        for (type_key, group_id), group in groups.items():
            if len(group["adjectives"]) != 4:
                raise ValueError(
                    f"Group {group_id} for {type_labels[type_key]} must have "
                    "exactly four adjectives."
                )
            exercise_key = (type_key, group["exercise_id"])
            if exercise_key in groups_by_type_and_exercise:
                raise ValueError(
                    f"Multiple adjective groups use exercise "
                    f"{group['exercise_id']} for {type_labels[type_key]}."
                )
            groups_by_type_and_exercise[exercise_key] = group

        seen_types = set()
        for row in image_rows:
            noun = _text(row["noun"])
            image_url = _text(row["adjectives_game_image_URL"])
            if not noun and not image_url:
                continue
            type_label = _text(row["adjective_type"])
            type_key = _slug(type_label)
            exercise_id = _text(row["exercise_id"])
            group = groups_by_type_and_exercise.get((type_key, exercise_id))
            if not group:
                raise ValueError(
                    f"Image row for {type_label!r} refers to an unknown "
                    f"exercise {exercise_id!r}."
                )
            if not noun or not image_url or not _text(
                row["adjectives_game_noun_audio_URL"]
            ):
                raise ValueError(
                    f"Image exercise {exercise_id} has an incomplete image "
                    "or noun audio URL."
                )

            adjective_by_id = {
                adjective["id"]: adjective for adjective in group["adjectives"]
            }
            panels = {}
            for position in ADJECTIVE_POSITIONS:
                adjective_id = _adjective_id(row[position])
                adjective = adjective_by_id.get(adjective_id)
                if not adjective:
                    raise ValueError(
                        f"Image for {noun!r} refers to unknown adjective "
                        f"ID {adjective_id!r} in {type_label}."
                    )
                panels[position] = {
                    "adjective_id": adjective["id"],
                    "adjective": adjective["word"],
                }

            group["exercises"].append({
                "noun": noun,
                "image_url": image_url,
                "noun_audio_url": _text(row["adjectives_game_noun_audio_URL"]),
                "panels": panels,
            })
            seen_types.add(type_key)

        types = []
        for type_key, type_label in type_labels.items():
            type_groups = [
                group
                for (group_type_key, _), group in groups.items()
                if group_type_key == type_key
            ]
            for group in type_groups:
                if not group["exercises"]:
                    raise ValueError(
                        f"Group {group['id']} for {type_label} has no images."
                    )
            types.append({
                "id": type_key,
                "label": type_label,
                "groups": [
                    {
                        "id": group["id"],
                        "label": f"Group {group['id']}",
                        "adjectives": group["adjectives"],
                        "exercises": group["exercises"],
                    }
                    for group in type_groups
                ],
            })

        if not types or seen_types != set(type_labels):
            raise ValueError("Adjectives game workbook has no complete exercises.")
        return {"types": types}
    finally:
        workbook.close()


def get_game_data():
    workbook_path = os.path.abspath(os.fspath(
        current_app.config.get("ADJECTIVES_ADVERBS_GAME_WORKBOOK", WORKBOOK_PATH)
    ))
    return _load_game_data(workbook_path)


@adjectives_adverbs_game_bp.route("/game")
def game_page():
    return render_template(
        "games/adjectives_adverbs_game.html",
        game_data=get_game_data(),
    )
