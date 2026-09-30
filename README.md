# Studio

Script-first workspace for creating, localizing, reviewing, and delivering vertical social video. The Studio is a local review library; it never exposes credentials or arbitrary repository files.

## Workspace contract

```text
config/       Brand, locale, profile, and workspace configuration
content/      One folder per content item; topic is metadata, never a folder name
scripts/      Reusable commands; agents call scripts instead of creating loose files
studio/       Local review application
runtime/      Generated media, API records, logs, and caches; not committed
input/        Private, local source material
```

`config/workspace.json` declares the default and favorite brands and active locales; put your own choices in the git-ignored `config/workspace.local.json` (see `scripts/workspace.py`). Brand rules go in `config/brands/<brand>/` (`brand.json`, `POLICY.md`); copy `config/brands/default` to start. A content record identifies its `name`, `brand`, `topic`, locales, and generator profile in `content.json`.

Create content only with the scaffold script:

```bash
python3 scripts/content/new_content.py --name phone-experiment --brand default --topic ai-booking --locales en,fa
python3 scripts/content/validate_content.py content/cnt-YYYYMMDD-phone-experiment
```

Every new final release is immutable and uses fixed filenames:

```text
content/<content-id>/releases/<locale>/v001/
  video.mp4
  caption.txt
  subtitles.srt
  cover.png
```

Existing content remains available under `content/` in its previous layout for provenance. New work must use the contract above; a later explicit migration can normalize each legacy record without deleting its generated media.

## Pipelines

`reel-main` is an orchestrator only. It depends on child pipelines in this order:

```text
intake → prompt → storyboard → video-generation → assembly → localization → subtitles → release
```

The child pipelines live in `config/pipelines/`. Every stage is a **prompt for the agent** (`prompt` field, with a `gate` of `none`, `approval` or `paid`). Studio does not show or run pipelines. Human and paid gates always stop for the user's yes. The main pipeline never calls a provider directly.

```bash
python3 scripts/content/pipeline.py init content/cnt-20260925-001
python3 scripts/content/pipeline.py plan content/cnt-20260925-001
python3 scripts/content/pipeline.py set-stage content/cnt-20260925-001 intake completed
```

## Agent request router

Every Studio request starts with the read-only router. It maps the
request to a known capability, child pipeline, entry script, required inputs,
and paid-operation status.

```bash
python3 scripts/agent/route_request.py "Create Persian subtitles for this Reel"
python3 scripts/agent/route_request.py --json "Make a Turkish Reel"
```

The enforcement rule for repository agents is in `AGENTS.md`. The registry is
`config/capabilities.json`; update it when adding an approved capability rather
than teaching individual agents a new ad-hoc workflow.

## Video generation

Before a paid request, list models and obtain an exact estimate:

```bash
python3 scripts/list_video_models.py
python3 scripts/estimate_video.py --request requests/default-text-to-video.json
python3 scripts/generate_video.py --request requests/default-text-to-video.json --wait
```

Generated Higgsfield videos are saved in `runtime/media/higgsfield/`; request, status, estimate, upload, error, and catalog records are saved under `runtime/higgsfield/`. HeyGen records are saved under `runtime/heygen/`.

## Source-video editing

Fastest path: drop videos in `input/videos/` and run `python3 scripts/content/ingest.py` (auto folder + topic). Exact prompts are in `PROMPTS.md`. Manual per-content import:

Put private, unedited source videos in `input/videos/`. When editing starts,
move—not copy—the selected source into its Content record:

```bash
python3 scripts/content/import_video.py \
  --content content/cnt-20260925-001 \
  --video input/videos/source-video.mp4
```

The script refuses overwrites and stores a SHA-256 import record beside the
video under `content/<content-id>/source/video/`.

## Studio

```bash
node studio/server.mjs
```

Open `http://localhost:8789/studio/`. Studio reads only registered release assets under `content/`; it supports legacy `finals/` bundles while new content uses `releases/`.
