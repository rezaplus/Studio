# Prompts: how to work with this workspace

Say these to the agent as written. Replace `<...>`. The agent always runs
`scripts/agent/route_request.py` first (see AGENTS.md).

## Folder map (only these matter)

```text
input/videos/     drop raw videos here (staging only)
content/<id>/     one folder per video, created automatically
studio/           review app  ->  node studio/server.mjs  ->  http://localhost:8789/studio/
config/           brands, locales, pipelines, capabilities  (rules, not media)
scripts/          every action is a script; agents never improvise
runtime/          generated media and provider records (not committed)
```

## 1. Add videos (automatic folder + topic)

1. Drop `.mp4/.mov/.m4v/.webm` files into `input/videos/`.
2. Say:

> Ingest the videos in input/videos.

This runs `python3 scripts/content/ingest.py`. For each video it creates
`content/cnt-<date>-<name>/`, moves the video to `source/video/` with a SHA-256
record, and writes `content.json` (name, topic, brand, locales) and `brief.md`
(size, duration, audio, 9:16 check).

- **Name and topic** come from the file name (`ai-booking-demo.mp4` → topic `ai-booking-demo`).
- Generic names (`IMG_1234`, `video-3`) get topic `unsorted`. Then say:

> Watch content/<id>/source/video, then set a real topic and name in content.json and brief.md.

- Preview only: `python3 scripts/content/ingest.py --dry-run`
- Override for one file: `--name my-name --topic my-topic`

## 2. Everyday prompts

| Goal | Say |
|---|---|
| Check a content item | `Validate content/<id>.` |
| Subtitles | `Create <fa/tr/ar/en> subtitles for content/<id>.` |
| Dub / translate | `Localize content/<id> to <tr/fa/ar>. Show the plan and price first.` |
| Show in Studio | `Register content/<id> as a <language> draft in Studio.` |
| Approve in Studio | `Promote content/<id> <delivery> to review.` (approved only on your explicit word) |
| Generate video (paid) | `Make a Reel for <brand>: topic ..., audience ..., duration ..., 9:16.` The agent asks the 7 intake questions, then storyboard, estimate, your approval. |
| Check a running job | `Check status of request <request_id>.` (never resubmits) |

## Batch (many videos)

Studio -> **Batch** page does all of this with buttons. Or say:

| Goal | Say |
|---|---|
| Ingest many | `Ingest the videos in input/videos.` |
| Word-by-word subtitles for all | `Create word-by-word subtitles for every content that has none.` (speech-to-text, checks script.txt if present, stops on mismatch) |
| Bulk dub (paid) | `Queue dubbing into <tr/fa/ar> for <content list>. Show balance and plan, then wait for my confirmation.` Runs one at a time; a second confirmation is needed per final render. |

## MCP (Higgsfield and HeyGen)

Connect HeyGen and Higgsfield once in the ChatGPT agent, then ask the agent to check the connection. Do not use Claude Code for this workspace.

| Goal | Say |
|---|---|
| Check connection | `Check that the Higgsfield and HeyGen MCP servers are connected.` |
| Free lookups | `Via MCP, list Higgsfield models and my HeyGen credits.` |
| Generate (paid) | `Via Higgsfield MCP, generate <shot>. Show model, settings and credit cost first.` |

MCP spends your plan credits, not the API wallet. Every paid call still stops for your yes.

## Arabic

Arabic is always Khaliji (Gulf) with an Emirati accent (`ar-AE`). Say: `Localize content/<id> to Arabic (Khaliji Emirati). Show the plan and price first.`

## Rules the agent follows

- Free actions (ingest, validate, subtitles, Studio) run immediately.
- Paid actions (Higgsfield, HeyGen) always stop for an exact estimate and your yes.
- Videos move out of `input/videos/`; nothing is copied into loose folders.
- Finals are immutable: `releases/<lang>/vNNN/` with `video.mp4`, `caption.txt`, optional `subtitles.srt`.
