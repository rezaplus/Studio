# Higgsfield Video Generation Agent

This repository is the local production workspace for generating videos through the Higgsfield API. Treat each generation as a paid, asynchronous external operation.

## Mandatory request routing

For every user request that concerns Studio work, run the read-only
router before selecting a workflow, creating files, or calling any provider:

```bash
python3 scripts/agent/route_request.py "<user request>"
```

Treat `config/capabilities.json` as the source of truth. Follow its resolution
order: **existing script → existing pipeline → profile/brand rules → agent
reasoning → provider**. Do not bypass an existing script or pipeline with an
ad-hoc agent action. If the router has no match, inspect existing capabilities
and scripts first; only then propose a new capability. A router result that has
`paid: true` never authorizes a paid operation: the normal estimate and explicit
approval gates still apply.

## Safety and credentials

- Read `.env` only locally; never print, commit, copy, or include the API key ID or secret in an answer.
- `.env` is created by the user from `.env.example`. Never create a real credential or attempt a paid request when credentials are absent.
- A video-generation `POST` can incur a charge. Before submitting, state the selected model, duration, resolution, aspect ratio, audio setting, and the exact prompt; ask for confirmation if any of those were not explicitly provided by the user.
- Do not blindly resubmit after timeouts, connection errors, or ambiguous responses. Inspect `runtime/higgsfield/requests/` and use `scripts/request_status.py REQUEST_ID` first, because the original request may already be running.

## Default flow

1. This workspace produces Instagram Reels only: use `9:16` by default. Do not switch to horizontal unless the user explicitly asks.
2. Turn the user's brief into a single clear video prompt. Preserve required product names, format, length, visual references, and sound requirements.
3. Use `requests/default-text-to-video.json` (or `requests/vertical-social.json`) as the 9:16 starting point. Copy or modify a request JSON only when a reusable preset is useful.
4. Before every paid submission, show the live video-model options and public rates with `python3 scripts/list_video_models.py`. Filter when useful, for example `--search kling`.
5. Before every paid submission, call `python3 scripts/estimate_video.py --request <file>` using the exact same model and payload. Present the returned estimate and get confirmation when the price was not already approved. The estimate, not the catalog rate, is authoritative for the selected configuration.
6. Submit with `python3 scripts/generate_video.py --request <file> --wait`.
7. For a request already submitted, never submit again merely to check its progress: run `python3 scripts/request_status.py <request_id>`.
8. Report the request ID and real local output path only after they are returned. A response URL alone is not a locally saved result.

## MCP providers (Higgsfield and HeyGen)

`.mcp.json` registers the official hosted MCP servers `higgsfield` (`https://mcp.higgsfield.ai/mcp`) and `heygen` (`https://mcp.heygen.com/mcp/v1/`). Sign in once with `/mcp` (browser OAuth); no key goes in `.env`.

- **Choose one transport per provider.** `HIGGSFIELD_MODE` and `HEYGEN_MODE` in `.env` (set in Studio Settings) are `api` or `mcp`, default `api`. The router prints them (`Provider modes:`). `api` = the scripts with `.env` keys; `mcp` = the MCP tools only. Use only the selected transport for that provider and never fall back to the other without the user's approval. API scripts refuse to run when their provider is set to `mcp` (`scripts/provider_mode.py`), and Studio's paid dubbing buttons do the same for HeyGen.
- MCP is a **provider transport, not a bypass**. The resolution order still applies: existing script/pipeline first; use an MCP tool only for something the scripts cannot do, or when the user asks for it.
- **Billing differs:** MCP spends the user's Higgsfield/HeyGen *plan credits* (OAuth), while the scripts use the API keys in `.env` (API wallet). State which one a step will use before spending.
- **Every generation, dubbing, translation or upload-and-render MCP tool is paid.** Apply the normal gates: exact model, duration, resolution, aspect ratio, audio, exact prompt, the credit cost the tool reports, then the user's explicit yes. Listing models, checking balance, status and history are free.
- `.claude/settings.json` forces a permission prompt for every `mcp__higgsfield*` and `mcp__heygen*` call. Do not widen it without the user's say-so.
- Never resubmit after a timeout: look up the existing job through the MCP status tool or `scripts/request_status.py` first.
- Download results into `runtime/` and record the job ID, tool used, settings and local path in the content folder; a provider URL alone is not a saved result. Brand, Arabic Khaliji/Emirati, glossary and two-confirmation dubbing rules apply unchanged.
- Check connection with `claude mcp list` (both should read connected).

## Batch work (many videos)

Studio's **Batch** page does all three; the agent uses the same scripts.

1. **Add videos:** files go to `input/videos/` (Studio upload or drop them there), then `python3 scripts/content/ingest.py` creates every content folder and topic. Free.
2. **Bulk subtitles (free, local):** `python3 scripts/content/subtitle_content.py --all-missing` (or `--content content/<id>`). Per content, in order: word-timed speech-to-text with the language auto-detected; if `script.txt`, `script.md` or `source/script.txt` exists, compare it with what was heard; below 80% match stop as `needs-review` and burn nothing; otherwise the subtitles are the STT words themselves, **one word per cue exactly as heard** (never the script text), burned with the locked `batimo` preset and registered as a Studio draft. Report every `needs-review` item and its differences.
3. **Bulk dubbing (paid, one at a time):**
   - `HEYGEN_MODE=api`: use the queue: `python3 scripts/dub_queue.py add --item PROJECT:RELEASE:LANG ... --yes-paid-proofread` (Studio must be running), then `list`, and after the user reviews each translated SRT, `render ID --yes-paid-render`. Studio's Batch page shows the same queue. Pass a `--yes-paid-*` flag only after the user's explicit yes for that exact list and step; show the HeyGen balance first (`dub_queue.py list`).
   - `HEYGEN_MODE=mcp`: no queue; process the items yourself strictly one at a time with the MCP tools, with the same two confirmations (Proofread for the list, final render per item after SRT review).
   - Never run items in parallel, never resubmit an `interrupted` or `failed` item without checking HeyGen for the existing job first, and stop the batch if the balance cannot cover the next item.

## Filesystem contract

- `requests/`: versionable, secret-free request payloads.
- `input/`: private local source material; do not commit it.
- `runtime/media/higgsfield/`: downloaded final videos; ignored by Git.
- `runtime/higgsfield/requests/`: submission records with model, input, and API response.
- `runtime/higgsfield/status/`: status responses.
- `runtime/higgsfield/errors/`: safe local diagnostics. Never write credentials to diagnostics.
- `runtime/higgsfield/estimates/`: cost previews; ignored by Git.
- `runtime/higgsfield/catalogs/`: timestamped live model/rate snapshots; ignored by Git.

## Studio workflow

- New videos in `input/videos/`: run `python3 scripts/content/ingest.py` (creates the content folder, derives name/topic, moves the video). If the topic comes out `unsorted`, inspect the video and set a real topic in `content.json`. User-facing prompts live in `PROMPTS.md`.
- Create every new item with `python3 scripts/content/new_content.py`; never create a loose content folder by hand.
- A content folder is named by a stable content ID, never by topic. Put `name`, `brand`, `topic`, locales, and generator profile in `content.json`.
- Read `config/workspace.json` (overlaid by the git-ignored `config/workspace.local.json`, see `scripts/workspace.py`) for the default brand and active locales. Brand-specific policy belongs in `config/brands/<brand>/`.
- Keep generated assets and provider records under `runtime/`; do not mix them with reusable configuration or source code.
- Stage private videos in `input/videos/`. At the start of editing, move the selected video into `content/<content-id>/source/video/` only through `scripts/content/import_video.py`; never copy it into a loose edit folder.
- Split a Reel into short, independently reviewable shots. Use live action for dialogue, exact product/UI, or identity-critical acting when possible; use Higgsfield only for the shots that benefit from generated motion.
- Create canonical and shot-specific stills in ChatGPT first. Upload only the chosen stills, then place their returned HTTPS URLs in the shot request.
- Use `python3 scripts/estimate_project.py <project>` for a no-network readiness report. After references are ready, use `--estimate` to obtain each exact API estimate and its total before any paid generation.
- Generate one approved shot at a time. Save its approved, screen-replaced version to the `final_path` stated in `project.json`.
- Use `python3 scripts/build_reel.py <project>` only after every `final_path` exists. It probes every clip, normalizes it to 1080x1920, and creates a silent visual assembly. Add real dialogue, authentic UI/screen replacement, captions, and sound in post.

## Mandatory Reel production policy

Apply this policy, in order, to **every new video request**. Do not skip a gate merely because a similar Reel was made before. A user can explicitly opt out of a step, but never assume that opt-out.

### 0. Intake: collect the creative brief first

When the user says “make a video” (or equivalent), do **not** begin generation or invent the creative brief. First ask for the brief under these headings, accepting a short free-form answer when the user prefers:

1. `Topic / core message` — the one idea the viewer should leave with.
2. `Audience and language` — intended viewers, spoken/on-screen language, and region if relevant.
3. `Format` — platform, desired duration, and aspect ratio (default Instagram Reel, 9:16).
4. `Creative direction` — visual style, characters, setting, required reference assets, and any example/restriction.
5. `Narrative and shot intent` — key beats, required shots, camera/motion, and the desired ending/CTA.
6. `Audio and postproduction` — voiceover/dialogue, music/SFX, captions, and UI/text that must be added in post.
7. `Budget and quality preference` — preview-only or final delivery, maximum budget if known, and any 480p/720p preference.

For current affairs or politics, also obtain the intended factual claims and their reliable sources, or explicitly label the work as opinion/satire. Do not create demographic-targeted political persuasion.

### 1. Create the production record before generating

1. Create `content/<content-id>/` with the scaffold script before any media/API work. New work uses `content.json`, `source/`, `storyboard/`, `shots/`, `production/`, `edit/`, `releases/`, and `archive/`.
2. Convert the brief into a shot list: story purpose, timeline duration, exact first-frame intent, motion, camera direction, audio/post requirements, and whether the shot is `live_action`, `higgsfield`, or `postproduction`.
3. Use `9:16` for Instagram Reels. Plan the edit delivery as 1080x1920 even when the generated preview uses a lower resolution.
4. Treat dialogue, precise product UI/text, and identity-critical performance as live action or postproduction by default. Use generated video only where generated motion adds value.

### 2. Approve the story before spending video credits

1. Produce a six-panel (or appropriately sized) **storyboard/keyframe sheet** with ChatGPT image generation. It is a cheap previsualization for narrative order, person/wardrobe, location, lighting, and camera framing.
2. The storyboard sheet is for human approval only. **Never upload a multi-panel collage as an image-to-video reference.**
3. After approval, create/export one clean, high-quality, vertical still for the first frame of each generated shot. Upload only those individual stills as API references.
4. Maintain a canonical character/wardrobe/location reference set, but supply the minimum images that the selected model requires. More references are not automatically better.

### 3. Budget and model gate

1. For every Higgsfield shot, record model, duration, resolution, aspect ratio, audio setting, reference URLs, and the reason that model was selected. Sound is an explicit Reel deliverable, not an afterthought. Native audio is a rate-affecting model option: when it is undecided, estimate both `generate_audio: true` and `generate_audio: false` variants before choosing.
2. List the live model catalog and check the selected model's official API reference. Use only fields that the current model explicitly supports.
3. Obtain an exact estimate from `scripts/estimate_video.py` for every ready payload, then total those estimates at project level with `scripts/estimate_project.py <project> --estimate`.
4. Present the model, settings, per-shot estimates, project total, and exact prompts to the user before the first paid submission. The API estimate is authoritative; catalog prices are only indicative.
5. Do not submit paid work until the user has approved the quoted configuration and cost. Do not resubmit an uncertain request; check its request ID first.

### 4. Low-cost preview gate

1. Start with a visual preview when its acceptance criteria are motion, visual continuity, camera, and frame quality only: use `480p`, `9:16`, the shortest model-supported duration (normally 2 seconds), and `generate_audio: false`. Before a final audiovisual chain, make a sound-enabled preview (`generate_audio: true`) for each distinct sound situation and compare its exact estimate. Review the sound as deliberately as the image.
2. Review each preview for the approved first frame, character and location consistency, intended motion, visual artifacts, and whether its final frame is usable as the next shot's start.
3. A 480p preview is sufficient to validate story, motion, and continuity. It is not automatically a final delivery decision.
4. Use 720p for a final branch only when phone review shows unacceptable softness, or the shot needs cropping, stabilization, detailed face work, or careful phone/screen tracking. Use 1080p only when its visible benefit justifies the extra cost.
5. Because dependent shots inherit real output frames, decide the final resolution for a whole dependent chain before creating that chain's final version. Do not expect a later higher-resolution shot to restore detail missing from an earlier 480p source.

### 5. Generate the approved chain one shot at a time

1. Generate only the approved current shot. Download it, record its request ID and local path, and make a small review/contact sheet if it helps select a frame.
2. Extract the **actual terminal frame** from the accepted current video. This actual frame—not a separately imagined storyboard panel—must become the `image_url`/first frame for the next generated shot.
3. Use a model's optional `end_image_url` only when an approved ending composition is genuinely needed for the current shot. It does not replace the rule above for the next shot.
4. If a shot is rejected or regenerated, stop the chain there. Reapprove its real final frame before generating downstream shots.
5. The **final Reel must have intentional audio**; it must not be silently published merely because the generated clips were silent. Once a shot's sound-enabled preview is approved, use native model audio for its final generation and include a concise sound direction in the prompt (ambience, physical action, timing, and what must not be heard). Mix the approved native audio with postproduction audio. Keep original dialogue, precise UI actions/notifications, branded claims, captions, and music under real recorded/licensed editorial control; do not rely on generated audio for those exact elements.

### 6. Final assembly and delivery gate

1. Lock the approved visual sequence, then create one **master audio timeline** for the whole Reel: dialogue, a single continuous music/ambience bed, and timed sound effects. Do not blindly concatenate the native audio from independent shots; retain only approved native segments and mix them beneath the master timeline.
2. Apply screen replacement, UI overlays, captions, authentic dialogue, and sound effects before marking each clip as final.
3. A single model-generated audiovisual take is an optional alternative only when the selected model explicitly supports multi-shot generation and native sound. Estimate and test it separately. Do not replace the sequential shot chain with it when exact first-frame handoff, product/UI accuracy, or per-shot review is more important than a continuous generated soundscape.
4. Use `scripts/build_reel.py <project>` only with approved final clips. Review the assembled Reel on a phone for 9:16 framing, safe zones, visual softness, continuity at every edit, and audio sync.
5. Preserve the storyboard, exact request JSON, estimates, request IDs, source references, terminal-frame handoffs, and final output paths inside the project folder. This makes the Reel reproducible and its cost auditable.

## API conventions

- Base URL: `https://api.higgsfield.ai`
- Authentication: `Authorization: Key <HF_API_KEY_ID>:<HF_API_KEY_SECRET>`
- Default model: `bytedance/seedance-2.0/text-to-video`
- Submit: `POST /<model>`; status: `GET /requests/<request_id>/status`.
- Model fields are model-specific. Before switching models or adding image/video/reference URLs, verify that model's current official API reference and retain only supported fields.

## Image references and first frames

- A local reference image must first be uploaded: `python3 scripts/upload_reference.py input/first-frame.jpg`. Use only the printed HTTPS `public_url`; local file paths are not accepted by Higgsfield generation endpoints.
- For a single starting frame, use `requests/reels-first-frame-wan-3.json` with `--model alibaba/wan-3.0/image-to-video`. Replace its `image_url` placeholder with the uploaded URL.
- For a first frame plus additional visual references, use `requests/reels-image-references-grok.json` with `--model xai/grok-imagine-video/v1.5/reference-to-video`. `image_url` is the first frame and `image_urls` holds additional reference images.
- Never submit a request containing `REPLACE_WITH_...`; upload or obtain the real HTTPS URL first. Always estimate the exact image-to-video payload before generating.

## Commands

```bash
cp .env.example .env
# Fill the two credentials in .env once.

python3 scripts/generate_video.py --request requests/default-text-to-video.json
python3 scripts/list_video_models.py
python3 scripts/list_video_models.py --search seedance
python3 scripts/estimate_video.py --request requests/default-text-to-video.json
python3 scripts/upload_reference.py input/first-frame.jpg
python3 scripts/estimate_video.py --model alibaba/wan-3.0/image-to-video --request requests/reels-first-frame-wan-3.json
python3 scripts/generate_video.py --model alibaba/wan-3.0/image-to-video --request requests/reels-first-frame-wan-3.json --wait
python3 scripts/generate_video.py --request requests/vertical-social.json --wait
python3 scripts/generate_video.py --prompt "A close-up of ..." --wait
python3 scripts/request_status.py REQUEST_ID
```

Run the model-list and estimate commands before every paid submission, using the exact same input. The live catalog price is indicative; the estimate endpoint returns the precise pre-submit amount. Use the first generation command without `--wait` to submit only. Use `--wait` only when the user wants the completed file in this workspace.

## Project-local skills

### Studio delivery contract

- Studio is the local results gallery in `studio/`, not an external AI studio. It discovers registered draft and release bundles under `content/<content-id>/`.
- A reviewable intermediate video does not need to be a final Release. Register it as an immutable `drafts/<language>/v<revision>/` bundle with status `draft`; Studio can display it before the full Reel is assembled. Keep each language's final delivery bundle separate. Name final videos with `reel-en`, `reel-fa`, `reel-tr`, or `reel-ar` and an explicit `vN` version; existing English exports without a language suffix default to English.
- New Studio deliveries use `content/<content-id>/deliverables.json` schemaVersion 1; follow `studio/README.md`. Register explicit video, optional post-caption and optional subtitle paths. Drafts live under `drafts/<language>/v<revision>/`; final delivery bundles use immutable `releases/<language>/v<revision>/` directories with `video.mp4`, UTF-8 `caption.txt` and optional `subtitles.srt`. Legacy `finals/` files remain readable only.
- For projects without a manifest, every final language directory must contain UTF-8 `caption.txt` beside its MP4. Legacy discovery reads that fixed filename, not versioned caption names.
- On-video subtitles and sidecar SRTs are separate assets, not post captions. Keep them separate and match the post CTA keyword to the language's video.
- When delivering a new final folder, carry forward or update its language-specific `caption.txt`. Do not copy another language's caption as a fallback.
- Append Studio deliveries rather than overwrite old bundles. Set `current[language]` explicitly; current is independent of status (`draft`, `review`, `approved`, `archived`). Promote a draft by changing its manifest status; never move or overwrite its immutable bundle. Do not mark approved without explicit editorial approval. Keep rejected versions archived for comparison.
- After a Studio registration, check `/api/results` at `http://localhost:8789` for the correct current draft/delivery. A final delivery needs a nonempty language-specific caption; a partial draft may intentionally omit one. Use Studio's Refresh button to reload. Never say content is visible merely because a caption file exists.

### Speech and dubbing

- For a Reel with cuts, several speakers, or only intermittent face visibility, never use one full-video translation followed by local target-language Speech-to-Text. Create a project-local `dubbing-plan.json` that splits only the spoken beats, assigns the exact speaker count for each beat, and uses HeyGen Precision Proofread per beat.
- Treat HeyGen's reviewed target SRT as the subtitle source. Merge those provider SRTs after the approved renders; do not replace their text with Whisper/faster-whisper output. Local STT may be used only to discover source-language timing when no approved source transcript exists.
- Require two paid confirmations in Studio: one before Proofread creation and another before the final renders. Keep the proofread SRTs accessible for review and preserve both the plan and job records under the project before assembly.
- Before creating localized speech, load `config/presenter-voices.json` if it exists (local and git-ignored; the template is `config/presenter-voices.example.json`). Reuse a recorded voice ID, engine, locale and settings when available. Preserve source/reference media locally.
- A translation job ID or source asset ID is not a reusable voice ID or avatar ID. Keep unavailable IDs null; do not claim a persistent avatar exists. Creating or cloning one is a separate operation requiring the user's authorization and the applicable provider workflow.
- Record voice changes and the scope of user approval in the registry. Voice-audition approval does not approve a full video. Verify pronunciation and lip-sync for each final delivery, and listen to any brand name before approval.
- Brand-specific rules (name pronunciation, glossary IDs, dialect targets, CTA keywords, subtitle style) live in `config/brands/<brand>/POLICY.md`. Read it for the content's brand and follow it; if it is absent, ask the user.

- For burned-in captions on a Reel or short-form video, read and follow `skills/reel-subtitles/SKILL.md`. The style comes from the content brand's `subtitlePreset` in `config/brands/<brand>/brand.json` (default `creator`); never switch a brand's preset without the user's approval.
- For local 720p upscaling, adaptive sharpening, natural color grading, and speed adjustments, read and follow `skills/reel-video-finishing/SKILL.md`.
- If a Codex session has not discovered it as an installed skill, read the project-local `SKILL.md` directly. After the repository is hosted on GitHub, it can be installed globally with:

  ```bash
  python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
    --repo OWNER/REPOSITORY --path skills/reel-subtitles
  ```

  Install the finishing skill after hosting with the same command, using `--path skills/reel-video-finishing`.
