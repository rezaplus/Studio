# Video Inbox

Drop raw videos here. Then tell the agent: **"Ingest the videos in input/videos."**

```bash
python3 scripts/content/ingest.py            # every video here
python3 scripts/content/ingest.py --dry-run  # preview names/topics only
python3 scripts/content/ingest.py clip.mp4 --topic ai-booking --name phone-test
```

Each video becomes `content/cnt-<date>-<name>/` with the video moved to
`source/video/`. Staging only: no renders or finals here. See `PROMPTS.md`.
