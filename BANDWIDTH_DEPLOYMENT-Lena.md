# Bandwidth optimization and gallery assets

## Class photo gallery

The `/gallery` page displays **class photos only**, with 12 thumbnails at a time; clicking one loads the full-size class photo. Exercise illustrations and vocabulary images are not shown in the gallery.

## Exercise image hosting

Set `PUBLIC_IMAGE_BASE_URL` in the hosting dashboard to the public root of an object store/CDN path containing the exercise image assets. The application rewrites exercise image URLs to use this host, preferring the optimized generated WebP derivative when one exists. For example, if an optimized image is at `https://cdn.example.com/course/gallery-thumbnails/vocab_game/example.webp`, set the variable to `https://cdn.example.com/course`. Keep the folder structure shown in the URLs. Image references not in the generated manifest (for example, workbook-supplied hint images) are mapped to their original path under the same external root.

Before enabling the variable, upload the non-class-photo contents of `static/images` and `static/gallery-thumbnails` to the external host, preserving their paths. Exclude `images/class_pics` and `gallery-thumbnails/class_pics`. Verify URLs in the vocabulary and other exercise flows; do not configure the variable until the files are public and reachable. If it is unset, exercises use local optimized thumbnails where available, preserving development and fallback behavior. The older `GALLERY_ASSET_BASE_URL` environment variable remains a compatibility fallback.

**Do not upload the class-photo folder** if only the images used in exercises should move off the app host. Class photos remain on the app host and are the only images in the gallery. Never place provider credentials in the repository or share them in chat.

## Generating exercise thumbnails

Regenerate the checked-in manifest and thumbnail files after adding or changing an image under `static/images`:

```powershell
.\.venv\Scripts\python.exe scripts\generate_gallery_thumbnails.py
```

Commit the updated `static/data/gallery_manifest.json` and files under `static/gallery-thumbnails` with the corresponding image changes. Pillow is listed in `requirements.txt` for this command; it is not used to process images during normal page requests.

## Cache behavior

The app compresses text responses of at least 500 bytes with Brotli when supported by the client, falling back to gzip. The public gallery document and ordinary Flask static files have a one-hour cache lifetime. Versioned gallery asset URLs and digest-named generated thumbnails receive a one-year immutable cache policy on the app host. Configure the external host to cache versioned exercise thumbnails for a year; do not recompress already-compressed image, audio, video, or PDF files.

## Deployment checks

After deploying, inspect the browser network panel for:

- No 42-image background burst on home, course, or contact.
- Only class photos appear in the gallery.
- Gallery thumbnails load as they approach the viewport, and full-size photos load only after selection.
- Exercise images load from the configured external host, if enabled.
- Lesson PDFs supporting range requests when the browser viewer seeks.
- Game audio/video still working, with the optional victory video not fetched until playback.

Compare transferred bytes on a fresh visit and a repeat visit. CDN offload reduces origin/app-host transfer but does not eliminate visitor data transfer and may have a separate CDN egress charge.
https://dash.cloudflare.com/d7553ce03d5c24eab2c9f1f628a5582e/r2/default/buckets/feliponetica