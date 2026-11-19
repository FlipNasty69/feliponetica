"""Loopback-only API for local Excel Feliponetica conversion."""
import os
from pathlib import Path

from flask import Flask, Response, request
from werkzeug.exceptions import RequestEntityTooLarge

os.environ.setdefault(
    "NLTK_DATA_PATH",
    str(Path.home() / "AppData" / "Local" / "Feliponetica" / "nltk_data"),
)

from features.feliponetica import convert_to_feliponetica_pollito

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


@app.post("/convert")
def convert():
    if request.mimetype != "text/plain":
        return Response(
            "Content-Type must be text/plain.\n",
            status=415,
            content_type="text/plain; charset=utf-8",
        )

    try:
        text = request.get_data(cache=False).decode("utf-8")
    except UnicodeDecodeError:
        return Response(
            "Request body must be valid UTF-8.\n",
            status=400,
            content_type="text/plain; charset=utf-8",
        )

    if not text.strip():
        return Response(
            "Text is required.\n",
            status=400,
            content_type="text/plain; charset=utf-8",
        )

    result = convert_to_feliponetica_pollito(text)
    return Response(result, content_type="text/plain; charset=utf-8")


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return Response(
        "Input exceeds the 64 KB limit.\n",
        status=413,
        content_type="text/plain; charset=utf-8",
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False, use_reloader=False)
