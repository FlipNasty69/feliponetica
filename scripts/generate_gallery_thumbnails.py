import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_ROOT = PROJECT_ROOT / "static" / "images"
THUMBNAIL_ROOT = PROJECT_ROOT / "static" / "gallery-thumbnails"
MANIFEST_PATH = PROJECT_ROOT / "static" / "data" / "gallery_manifest.json"
SUPPORTED_FORMATS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
THUMBNAIL_SIZE = (640, 480)


def display_name(relative_path):
    stem = relative_path.stem
    if relative_path.parts[0] == "class_pics":
        match = re.search(r"\((\d+)\)", stem)
        return f"Class photo {match.group(1)}" if match else "Class photo"
    return re.sub(r"[_-]+", " ", stem).strip().capitalize()


def category_name(relative_path):
    folder = relative_path.parts[0] if len(relative_path.parts) > 1 else ""
    categories = {
        "class_pics": "Class photos",
        "popups": "Course illustrations",
        "vocab_game": "Vocabulary pictures",
    }
    return categories.get(folder, "Site artwork")


def source_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_thumbnail(source_path, thumbnail_path):
    with Image.open(source_path) as original:
        image = ImageOps.exif_transpose(original)
        dimensions = image.size
        image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        if "A" in image.getbands():
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(thumbnail_path, format="WEBP", quality=72, method=6)
        return dimensions


def main():
    items = []
    for source_path in sorted(IMAGE_ROOT.rglob("*")):
        if not source_path.is_file() or source_path.suffix.lower() not in SUPPORTED_FORMATS:
            continue

        relative_path = source_path.relative_to(IMAGE_ROOT)
        digest = source_digest(source_path)
        if source_path.suffix.lower() == ".avif":
            thumbnail_relative = Path("images") / relative_path
            with Image.open(source_path) as image:
                width, height = ImageOps.exif_transpose(image).size
        else:
            thumbnail_name = f"{source_path.stem}-{digest[:12]}.webp"
            thumbnail_path = (
                THUMBNAIL_ROOT / relative_path.parent / thumbnail_name
            )
            width, height = make_thumbnail(source_path, thumbnail_path)
            thumbnail_relative = (
                Path("gallery-thumbnails") / relative_path.parent / thumbnail_name
            )

        items.append({
            "source": (Path("images") / relative_path).as_posix(),
            "thumbnail": thumbnail_relative.as_posix(),
            "version": digest[:16],
            "name": display_name(relative_path),
            "category": category_name(relative_path),
            "width": width,
            "height": height,
        })

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(items)} gallery entries in {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
