import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from flask import Blueprint, abort, current_app, render_template, url_for


gallery_bp = Blueprint("gallery", __name__)
GALLERY_MANIFEST = (
    Path(__file__).resolve().parent / "static" / "data" / "gallery_manifest.json"
)


@lru_cache(maxsize=1)
def _gallery_items_by_source():
    with GALLERY_MANIFEST.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)
    return {item["source"]: item for item in manifest["items"]}


def _public_asset_base_url():
    return (
        current_app.config.get("PUBLIC_ASSET_BASE_URL")
        or current_app.config.get("PUBLIC_IMAGE_BASE_URL")
        or current_app.config.get("GALLERY_ASSET_BASE_URL", "")
    ).strip()


def _asset_url(filename, version=None):
    base_url = _public_asset_base_url()
    if base_url:
        parsed_url = urlsplit(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise RuntimeError(
                "PUBLIC_ASSET_BASE_URL must be an absolute HTTP(S) URL."
            )
        asset_url = f"{base_url.rstrip('/')}/{quote(filename, safe='/')}"
    else:
        asset_url = url_for("static", filename=filename)

    if version:
        asset_url = f"{asset_url}?v={quote(version, safe='')}"
    return asset_url


def public_audio_url(source_url):
    parsed_url = urlsplit(source_url)
    if parsed_url.scheme or parsed_url.netloc:
        return source_url

    source_path = unquote(parsed_url.path.lstrip("/"))
    if not source_path.startswith("static/audio/"):
        return source_url

    asset_path = source_path[len("static/"):]
    original_asset_path = asset_path
    legacy_prefix = "audio/pronunciation audio/"
    if asset_path.startswith(legacy_prefix):
        asset_path = "audio/verb_conjugation/" + asset_path[len(legacy_prefix):]

    if not _public_asset_base_url():
        if asset_path == original_asset_path:
            return source_url
        local_path = f"/static/{quote(asset_path, safe='/')}"
        return urlunsplit(("", "", local_path, parsed_url.query, parsed_url.fragment))

    asset_url = _asset_url(asset_path)
    return urlunsplit(
        urlsplit(asset_url)._replace(
            query=parsed_url.query,
            fragment=parsed_url.fragment,
        )
    )


def exercise_image_url(source_url):
    parsed_url = urlsplit(source_url)
    if parsed_url.scheme or parsed_url.netloc:
        return source_url

    source_path = unquote(parsed_url.path.lstrip("/"))
    if not source_path.startswith("static/images/"):
        return source_url

    image_path = source_path[len("static/"):]
    if image_path.startswith("images/class_pics/"):
        return _asset_url(image_path) if _public_asset_base_url() else source_url

    item = _gallery_items_by_source().get(image_path)
    base_url = _public_asset_base_url()
    if base_url:
        if item:
            return _asset_url(item["thumbnail"], item["version"])
        return _asset_url(image_path)

    if item:
        return _asset_url(item["thumbnail"], item["version"])
    return source_url


@gallery_bp.get("/gallery")
def gallery_page():
    try:
        manifest_items = list(_gallery_items_by_source().values())
    except FileNotFoundError:
        current_app.logger.exception("Gallery manifest is missing.")
        abort(500, description="The image gallery is not available.")
    except json.JSONDecodeError:
        current_app.logger.exception("Gallery manifest is invalid.")
        abort(500, description="The image gallery is not available.")

    items = [
        {
            **item,
            "thumbnail_url": _asset_url(item["thumbnail"]),
            "image_url": _asset_url(item["source"], item["version"]),
        }
        for item in manifest_items
        if item["category"] == "Class photos"
    ]
    return render_template(
        "gallery.html",
        gallery_items=items,
    )
