# Bandwidth optimization and gallery assets

## Class photo gallery

The `/gallery` page displays **class photos only**, with 12 thumbnails at a time; clicking one loads the full-size class photo. Exercise illustrations and vocabulary images are not shown in the gallery.

## Cloudflare static assets

The app can serve class photos, vocabulary and “along” exercise images, generated thumbnails, and audio from one public Cloudflare base URL. Set `PUBLIC_ASSET_BASE_URL` in the hosting dashboard to the public URL for the root of the bucket (without a trailing slash). Keep the relative paths below when uploading:

| App asset | Object key path |
| --- | --- |
| Verb-conjugation audio | `audio/verb_conjugation/` |
| Game feedback audio | `audio/game_feedback/` |
| Vocabulary-game audio | `audio/vocab_game/` |
| Class photos | `images/class_pics/` |
| Course popups/illustrations | `images/popups/` |
| Vocabulary-game images | `images/vocab_game/`, including its `along a lo largo/` subfolder |
| Generated image thumbnails | `gallery-thumbnails/`, retaining the corresponding image subfolders |

For example, if `audio/vocab_game/I.mp3` is publicly available at `https://media.example.com/audio/vocab_game/I.mp3`, set `PUBLIC_ASSET_BASE_URL` to `https://media.example.com`. The same base URL must also serve the other paths in the table. The bucket does not have generated thumbnails yet; the generated files are already present locally under `static/gallery-thumbnails`. Upload those as `gallery-thumbnails/...` alongside the originals. If any source images change before upload, regenerate the thumbnails using the command below first. The gallery and games use these derivatives where available, while full-size originals remain available for the gallery and as a fallback for images without derivatives.

Upload the files used by the app, preserving these paths, and enable the setting only after representative objects are publicly reachable. When unset, the app uses its own static files and optimized local exercise thumbnails. `PUBLIC_IMAGE_BASE_URL` and the older `GALLERY_ASSET_BASE_URL` are supported as compatibility fallbacks.

Only class photos appear in the gallery; other images remain in their exercise contexts. The same base URL must map both image and audio folder paths. Treat every uploaded object as public: anyone who can access its URL can view or download it. Do not upload sensitive or private student materials. Never place provider credentials in the repository or share them in chat.

The conjugation game checks for audio files with browser `fetch` requests before showing playback controls. Configure the bucket's CORS policy to allow `GET` and `HEAD` from the deployed app's origin (and local development origin, if needed); otherwise the files may be publicly reachable but those checks will fail in the browser.

## Generating exercise thumbnails

Regenerate the checked-in manifest and thumbnail files after adding or changing an image under `static/images`:

```powershell
.\.venv\Scripts\python.exe scripts\generate_gallery_thumbnails.py
```

Commit the updated `static/data/gallery_manifest.json` and files under `static/gallery-thumbnails` with the corresponding image changes. Pillow is listed in `requirements.txt` for this command; it is not used to process images during normal page requests.

## Cache behavior

The app compresses text responses of at least 500 bytes with Brotli when supported by the client, falling back to gzip. The public gallery document and ordinary Flask static files have a one-hour cache lifetime. Versioned gallery asset URLs and digest-named generated thumbnails receive a one-year immutable cache policy on the app host. Configure Cloudflare to cache generated thumbnails for a year; do not recompress already-compressed image, audio, video, or PDF files.

## Deployment checks

After deploying, inspect the browser network panel for:

- No 42-image background burst on home, course, or contact.
- Only class photos appear in the gallery.
- Gallery thumbnails load as they approach the viewport, and full-size photos load only after selection.
- Class photos, vocabulary/“along” images, and audio load from the configured external host, if enabled.
- Lesson PDFs supporting range requests when the browser viewer seeks.
- Game audio/video still working, with the optional victory video not fetched until playback.

Compare transferred bytes on a fresh visit and a repeat visit. CDN offload reduces origin/app-host transfer but does not eliminate visitor data transfer and may have a separate CDN egress charge.
