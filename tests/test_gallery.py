import gzip
import json
from pathlib import Path

import brotli
from PIL import Image

from app import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "static" / "data" / "gallery_manifest.json"


def test_gallery_renders_class_photos_only():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    class_photos = [
        item for item in manifest["items"] if item["category"] == "Class photos"
    ]
    response = app.test_client().get("/gallery")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.count('class="gallery-card"') == len(class_photos)
    assert 'loading="lazy"' in html
    assert response.headers["Cache-Control"] == "public, max-age=3600"
    assert "class photos" in html
    assert "Vocabulary pictures" not in html
    assert "Course illustrations" not in html
    assert all(
        (PROJECT_ROOT / "static" / item["thumbnail"]).is_file()
        for item in manifest["items"]
    )


def test_gallery_derivatives_reduce_image_bytes_by_at_least_80_percent():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    items_with_local_sources = [
        item
        for item in manifest["items"]
        if (PROJECT_ROOT / "static" / item["source"]).is_file()
    ]
    assert items_with_local_sources
    originals_bytes = sum(
        (PROJECT_ROOT / "static" / item["source"]).stat().st_size
        for item in items_with_local_sources
    )
    thumbnails_bytes = sum(
        (PROJECT_ROOT / "static" / item["thumbnail"]).stat().st_size
        for item in items_with_local_sources
    )

    assert thumbnails_bytes < originals_bytes * 0.2
    for item in manifest["items"]:
        if item["thumbnail"].startswith("gallery-thumbnails/"):
            with Image.open(PROJECT_ROOT / "static" / item["thumbnail"]) as image:
                assert image.width <= 640
                assert image.height <= 480


def test_gallery_uses_external_host_for_class_photos_when_configured(monkeypatch):
    monkeypatch.setitem(
        app.config,
        "PUBLIC_ASSET_BASE_URL",
        "https://cdn.example.test/course",
    )

    response = app.test_client().get("/gallery")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-src="https://cdn.example.test/course/gallery-thumbnails/class_pics/' in html
    assert 'data-full-image="https://cdn.example.test/course/images/class_pics/' in html


def test_vocabulary_game_api_uses_optimized_image_derivatives():
    response = app.test_client().get("/vocab/api/get-set-details?id=3.2")
    words = response.get_json()
    image_urls = [
        image
        for word in words
        for image in word.get("images", [word.get("image")])
        if image
    ]
    optimized_urls = [
        image_url for image_url in image_urls if "/static/gallery-thumbnails/" in image_url
    ]
    client = app.test_client()

    assert response.status_code == 200
    assert optimized_urls
    assert all(client.get(image_url).status_code == 200 for image_url in optimized_urls)


def test_exercise_images_use_external_host_when_configured(monkeypatch):
    monkeypatch.setitem(
        app.config,
        "PUBLIC_ASSET_BASE_URL",
        "https://cdn.example.test/course",
    )

    response = app.test_client().get("/vocab/api/get-set-details?id=3.2")
    words = response.get_json()
    image_urls = [
        image
        for word in words
        for image in word.get("images", [word.get("image")])
    ]

    assert response.status_code == 200
    assert all(
        image_url.startswith("https://cdn.example.test/course/")
        for image_url in image_urls
    )
    assert any(
        "/gallery-thumbnails/" in image_url for image_url in image_urls
    )


def test_popup_and_along_images_use_external_host_with_bucket_paths(monkeypatch):
    from gallery import exercise_image_url

    monkeypatch.setitem(
        app.config,
        "PUBLIC_ASSET_BASE_URL",
        "https://cdn.example.test/course",
    )
    with app.test_request_context("/"):
        popup_url = exercise_image_url(
            "/static/images/popups/pollito.webp"
        )
        along_url = exercise_image_url(
            "/static/images/vocab_game/along%20a%20lo%20largo/board.webp"
        )

    assert popup_url.startswith(
        "https://cdn.example.test/course/gallery-thumbnails/popups/"
    )
    assert along_url.startswith(
        "https://cdn.example.test/course/gallery-thumbnails/"
        "vocab_game/along%20a%20lo%20largo/"
    )


def test_external_host_maps_unindexed_exercise_images_to_source_path(monkeypatch):
    from gallery import exercise_image_url

    monkeypatch.setitem(
        app.config,
        "PUBLIC_ASSET_BASE_URL",
        "https://cdn.example.test/course",
    )
    with app.test_request_context("/"):
        assert exercise_image_url(
            "/static/images/phantom_pronouns/verbs/querer.webp"
        ) == "https://cdn.example.test/course/images/phantom_pronouns/verbs/querer.webp"


def test_vocabulary_audio_uses_external_host_when_configured(monkeypatch):
    monkeypatch.setitem(
        app.config,
        "PUBLIC_ASSET_BASE_URL",
        "https://cdn.example.test/course",
    )

    response = app.test_client().get("/vocab/api/get-set-details?id=1")
    words = response.get_json()

    assert response.status_code == 200
    assert all(
        word["audio"].startswith("https://cdn.example.test/course/audio/")
        for word in words
    )


def test_external_host_maps_legacy_conjugation_audio_to_r2_folder(monkeypatch):
    from gallery import public_audio_url

    monkeypatch.setitem(
        app.config,
        "PUBLIC_ASSET_BASE_URL",
        "https://cdn.example.test/course",
    )
    with app.test_request_context("/"):
        assert public_audio_url(
            "/static/audio/pronunciation%20audio/FB_hit.mp3"
        ) == "https://cdn.example.test/course/audio/verb_conjugation/FB_hit.mp3"


def test_legacy_conjugation_audio_maps_to_r2_folder_with_local_fallback(monkeypatch):
    from gallery import public_audio_url

    monkeypatch.setitem(app.config, "PUBLIC_ASSET_BASE_URL", "")
    monkeypatch.setitem(app.config, "PUBLIC_IMAGE_BASE_URL", "")
    source_url = "/static/audio/pronunciation%20audio/FB_hit.mp3"

    with app.test_request_context("/"):
        assert public_audio_url(source_url) == (
            "/static/audio/verb_conjugation/FB_hit.mp3"
        )

        monkeypatch.setitem(
            app.config,
            "PUBLIC_ASSET_BASE_URL",
            "https://cdn.example.test/course/",
        )
        assert public_audio_url(source_url) == (
            "https://cdn.example.test/course/audio/verb_conjugation/FB_hit.mp3"
        )


def test_legacy_vocabulary_route_redirects_to_numbered_set_selector():
    response = app.test_client().get("/vocab/picture-match/along")

    assert response.status_code == 302
    assert response.headers["Location"] == "/vocab/game"
    game_response = app.test_client().get(response.headers["Location"])
    assert game_response.status_code == 200
    assert b'id="setSelect"' in game_response.data
    assert b"Set 1" in game_response.data


def test_versioned_gallery_assets_receive_immutable_cache_policy():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    item = manifest["items"][0]
    client = app.test_client()

    thumbnail_response = client.get(f"/static/{item['thumbnail']}")
    original_response = client.get(
        f"/static/{item['source']}?v={item['version']}"
    )

    assert thumbnail_response.status_code == 200
    assert original_response.status_code == 200
    assert thumbnail_response.headers["Cache-Control"] == (
        "public, max-age=31536000, immutable"
    )
    assert original_response.headers["Cache-Control"] == (
        "public, max-age=31536000, immutable"
    )


def test_text_responses_are_gzipped_when_supported_by_the_client():
    client = app.test_client()
    response = client.get(
        "/gallery",
        headers={"Accept-Encoding": "gzip"},
    )
    brotli_response = client.get(
        "/gallery",
        headers={"Accept-Encoding": "br"},
    )

    assert response.headers["Content-Encoding"] == "gzip"
    assert len(response.data) < 50_000
    assert b"Picture Gallery" in gzip.decompress(response.data)
    assert brotli_response.headers["Content-Encoding"] == "br"
    assert len(brotli_response.data) < len(response.data)
    assert b"Picture Gallery" in brotli.decompress(brotli_response.data)


def test_home_page_no_longer_requests_background_photo_burst():
    response = app.test_client().get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-image-count="42"' not in html
    assert "background_engine.js" not in html


def test_lesson_pdf_supports_range_requests():
    response = app.test_client().get(
        "/lesson-pdf/Waiter Poem flap.pdf",
        headers={"Range": "bytes=0-99"},
    )

    assert response.status_code == 206
    assert response.headers["Content-Range"].startswith("bytes 0-99/")
    assert len(response.data) == 100
