# Studio results gallery

Run `node studio/server.mjs` from the project root, then open http://localhost:8789/studio/.

Local gallery and localization workspace. It never exposes keys or repository
files. It can display an immutable registered `draft` before a final Reel is
assembled; a Draft is review material, not a release or approval. The optional
subtitle job runs locally: it transcribes the selected delivery, compares the recognized wording to an expected script, creates
phrase-level SRT captions from the recognized speech, and registers a new
review draft. The expected script is QA only, never subtitle source text.

The dubbing action uses the configured HeyGen CLI only after the user checks
the paid-request acknowledgement in Studio. It uses precision mode, keeps the
same format, asks for the real speaker count, then runs the same local STT and
script-QA process on the **dubbed output** before registering a review draft.
The user supplies the expected translated script and localized post caption;
neither is silently machine-invented. HeyGen does not return a cost estimate
through the CLI, so Studio states that limitation before the confirmation.
Discovers registered videos under `content/<content-id>/`, grouped by content item.
English, Persian, Turkish and Arabic versions are labeled and filterable.
The monochrome library shows the shared topic cover (or a placeholder when missing).
Click a topic to open its detail page with one video player, a language switcher,
the full available caption, cover links, filename, duration and resolution.
Detail pages have a topic hash URL and support browser back navigation.
Projects with `deliverables.json` use explicit draft/delivery metadata. The language
switcher defaults to the delivery selected in `current`; the Version selector
includes registered history and shows draft/review/approved/archived status. Current
does not mean approved. Missing assets and invalid manifests show warnings.
Projects without a manifest retain legacy latest-filename discovery.

Manifest captions come from each delivery's explicit `caption` path. A Draft
may intentionally omit a post caption. Legacy
captions are read from `caption.txt` beside each video. Missing captions are
marked, not copied from another language. In a project detail page, each
language can have its own cover. Uploading one saves it locally under
`assets/cover/<language>/` and records it in the manifest; the shared project
cover remains the library-card fallback. Only discovered deliverables are served;
credentials and other repository files are not exposed. Video seeking is supported.

## Versioned delivery contract (recommended)

Use `content/<content-id>/deliverables.json`, schema version 1. Paths are
relative to the content folder; videos, captions and subtitles must be inside
`drafts/`, `releases/`, or retained legacy `finals/`. Absolute paths, traversal
and symlinks escaping the content folder are rejected.
An invalid manifest does not silently fall back to filename guessing.

```json
{
  "schemaVersion": 1,
  "title": "My Reel",
  "cover": "releases/en/v001/cover.png",
  "covers": {"tr": "assets/cover/tr/cover-2026.png"},
  "current": {"tr": "tr-v2"},
  "releases": [
    {
      "id": "tr-v2",
      "language": "tr",
      "version": 2,
      "status": "review",
      "label": "Subtitles + timer",
      "video": "releases/tr/v002/video.mp4",
      "caption": "releases/tr/v002/caption.txt",
      "subtitles": "releases/tr/v002/subtitles.srt",
      "notes": "Check brand pronunciation before publishing."
    }
  ]
}
```

Use immutable bundles for new work. A partial or pre-assembly output belongs in
`drafts/<language>/v<revision>/`; it may omit the post caption. A finished
delivery belongs in `releases/<language>/v<revision>/` and keeps `video.mp4`,
`caption.txt`, and optional `subtitles.srt`/`cover.png` together. Append a
delivery with a unique id and increasing language-specific version. Set
`current[language]` deliberately; a larger number alone never promotes a
delivery. A draft can move through `draft`, `review`, `approved`, and
`archived` by updating its manifest status; do not move or overwrite the
immutable bundle. Set `approved` only after explicit editorial approval.
Archive rejected/superseded versions instead of deleting their assets.

Legacy `finals/` bundles remain readable to preserve provenance. New work uses
`drafts/` for intermediate review and `releases/` for final delivery bundles.

## Legacy folder contract

Keep one language per final delivery folder, for example:

```text
content/<content-id>/finals/
  instagram-reel-tr-precision-v2/
    batimo-reel-tr-subtitles-timer-brand-fixed-v4.mp4
    caption.txt
    subtitles-tr-v3.srt
```

The video version can advance within the same folder. `caption.txt` always holds
the current post caption for that language. Files such as `caption-tr-v4.txt`
are archives and are not used by the gallery. Burned-in subtitles or SRT files
do not replace the post caption. Each new delivery folder needs its own
`caption.txt`; keep its CTA keyword consistent with its video.

Verify the selected videos and captions through `GET /api/results`, then click
Refresh in Studio. No restart is required for new deliverables or caption files.

## Tests and scaling

Run `node --test studio/catalog.test.mjs`. Manifest projects read registered
paths only, rather than recursively scanning every render. Refresh rebuilds
the catalog from disk, with no persistent cache to become stale. Legacy projects
still scan their final folders. The local server serves only discovered assets.
Its local cover endpoint accepts a PNG, JPEG, or WebP up to 10 MB, verifies its
file signature, and updates only the chosen language cover in the manifest. It
does not publish externally.
