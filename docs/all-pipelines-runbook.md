# Transcription Engine — All Pipelines Runbook

> **What this document covers:** End-to-end, step-by-step instructions to run every pipeline in this project sequentially — from a fresh checkout to fully processed transcripts and audio episodes.

---

## Table of Contents

1. [Step 0 — One-Time Setup (do this first, every pipeline needs it)](#step-0--one-time-setup)
2. [Pipeline 1 — Transcription Pipeline](#pipeline-1--transcription-pipeline)
   - [1A. Manual: Transcribe a single YouTube video via CLI](#1a-manual-transcribe-a-single-youtube-video-via-cli)
   - [1B. Manual: Transcribe via HTTP API](#1b-manual-transcribe-via-http-api)
3. [Pipeline 2 — Automated Ingestion Pipeline](#pipeline-2--automated-ingestion-pipeline)
   - [2A. Seed content sources](#2a-seed-content-sources)
   - [2B. Scan → Classify → Queue (individually)](#2b-scan--classify--queue-individually)
   - [2C. Scan → Classify → Queue (one shot)](#2c-scan--classify--queue-one-shot)
   - [2D. Start transcription on queued items](#2d-start-transcription-on-queued-items)
4. [Pipeline 3 — Audiobook Pipeline](#pipeline-3--audiobook-pipeline)
   - [3A. Prepare input files](#3a-prepare-input-files)
   - [3B. Run the audiobook curator](#3b-run-the-audiobook-curator)
   - [3C. Query generated playlists via API](#3c-query-generated-playlists-via-api)
5. [Quick Reference — All Commands End-to-End](#quick-reference--all-commands-end-to-end)
6. [Configuration Reference](#configuration-reference)
7. [Troubleshooting](#troubleshooting)

---

## Step 0 — One-Time Setup

> **Do this once** before running any pipeline. All three pipelines share the same environment.

### 0.1 Clone the repository

```bash
git clone https://github.com/staru09/transcription_engine.git
cd transcription_engine
```

### 0.2 Create a virtual environment and install dependencies

```bash
# Using pip
python -m venv venv
source venv/bin/activate       # Linux / macOS
# venv\Scripts\activate        # Windows

pip install -r requirements.txt
```

> **Alternative — using uv (faster):**
> ```bash
> uv venv
> uv pip install -r requirements.txt
> source .venv/bin/activate
> ```

### 0.3 Install system dependencies

`ffmpeg` is required for both audio download and audiobook stitching:

```bash
# Ubuntu / Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
winget install Gyan.FFmpeg
```

### 0.4 Configure environment variables

```bash
cp env.example .env
```

Open `.env` and fill in your keys. The table below shows which pipelines need each key:

| Variable | Pipeline 1 | Pipeline 2 | Pipeline 3 | Purpose |
|---|---|---|---|---|
| `DATABASE_URL` | ✅ | ✅ | ✅ | PostgreSQL connection string |
| `GOOGLE_API_KEY` | ✅ (correction/summary) | ✅ (classification) | — | Gemini LLM |
| `YOUTUBE_API_KEY` | — | ✅ | — | Channel scanning |
| `DEEPGRAM_API_KEY` | ✅ if using Deepgram | ✅ if using Deepgram | ✅ if using Deepgram TTS |
| `SMALLEST_API_KEY` | ✅ if using SmallestAI | ✅ if using SmallestAI | ✅ if using SmallestAI TTS |
| `OPENAI_API_KEY` | ✅ (LLM correction) | — | ✅ (LLM chapterization) |
| `SUPABASE_URL` | — | — | Optional (CDN upload) |
| `SUPABASE_KEY` | — | — | Optional (CDN upload) |

Minimum `.env` to run all three pipelines:

```env
DATABASE_URL=postgresql://bitcoin:bitcoin@127.0.0.1:5434/transcription_engine
GOOGLE_API_KEY=your_google_key
YOUTUBE_API_KEY=your_youtube_key
DEEPGRAM_API_KEY=your_deepgram_key
OPENAI_API_KEY=your_openai_key
```

### 0.5 Start PostgreSQL

**Option A — Local Docker (recommended for development):**

```bash
docker compose up -d postgres
```

Data persists in the `postgres_data` Docker volume. To wipe it: `docker compose down -v`.

**Option B — AWS RDS or any remote Postgres:**

Set `DATABASE_URL` in `.env` to your remote connection string. No extra steps needed.

### 0.6 Initialize the database schema

Run this **once** to create all tables (transcripts, ingestion, and audiobook tables):

```bash
# Core transcription tables
tstbtc db init

# Audiobook tables (audio_playlists, audio_episodes)
python scripts/migrate_schema.py
```

Verify connectivity at any time:

```bash
tstbtc db check
```

### 0.7 Start the FastAPI server

The server must be running for all API-based workflows. The CLI auto-starts it, but you can also start it manually:

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## Pipeline 1 — Transcription Pipeline

**What it does:** Takes a YouTube URL or local audio file → downloads audio → STT (Whisper / Deepgram / SmallestAI) → LLM correction → LLM summarization → saves to DB and/or Markdown.

```
YouTube URL / local file
       │
  [Preprocess] ──▶ Download video, extract audio (FFmpeg)
       │
  [Transcribe] ──▶ STT (Whisper / Deepgram / SmallestAI)
       │
  [Metadata Extraction] ──▶ Gemini LLM (speakers, conference, topics)
       │
  [Correction] ──▶ Gemini LLM (fix ASR errors, technical terms)
       │
  [Summarization] ──▶ Gemini LLM (structured summary)
       │
  [Postprocess] ──▶ Export Markdown + save to PostgreSQL
```

### 1A. Manual: Transcribe a single YouTube video via CLI

> The CLI auto-starts the FastAPI server in the background, so you only need one terminal.

**With Deepgram (recommended — fastest, best accuracy):**

```bash
tstbtc transcribe "https://www.youtube.com/watch?v=VIDEO_ID" \
  --deepgram \
  --diarize \
  --markdown \
  --correct \
  --summarize \
  --llm-provider google \
  --loc "tabconf" \
  --username "your_name"
```

**With SmallestAI (multi-speaker, emotion detection):**

```bash
tstbtc transcribe "https://www.youtube.com/watch?v=VIDEO_ID" \
  --smallestai \
  --diarize \
  --markdown \
  --correct \
  --summarize \
  --llm-provider google \
  --loc "tabconf" \
  --username "your_name"
```

**With Whisper (local, no cloud STT key required):**

```bash
tstbtc transcribe "https://www.youtube.com/watch?v=VIDEO_ID" \
  --markdown \
  --username "your_name"
```

**Transcribe a local audio file:**

```bash
tstbtc transcribe "/path/to/talk.mp3" \
  --deepgram \
  --diarize \
  --markdown \
  --username "your_name"
```

**Common CLI flags:**

| Flag | Description |
|---|---|
| `--deepgram` | Use Deepgram cloud STT |
| `--smallestai` | Use SmallestAI cloud STT |
| (neither) | Use local Whisper |
| `--diarize` | Enable speaker diarization |
| `--markdown` | Save output as Markdown file |
| `--correct` | Run LLM correction pass |
| `--summarize` | Generate LLM summary |
| `--llm-provider google` | Use Gemini for LLM steps |
| `--loc <slug>` | Location/category (e.g. `tabconf`, `misc`) |
| `--username <name>` | Submitter username |

**Output locations:**

| What | Where |
|---|---|
| Markdown transcript | `local_models/<loc>/<slug>.md` |
| Raw STT output + metadata | `metadata/<loc>/<slug>/` |
| Database row | `transcripts` table |

> **Note on switching STT providers:** The server caches the provider on the first request. To switch (e.g. from Deepgram to SmallestAI), run:
> ```bash
> tstbtc server stop
> # then re-run tstbtc transcribe with the new provider flag
> ```

### 1B. Manual: Transcribe via HTTP API

Use this if you want to integrate from another service or script multiple videos.

**Step 1 — Start the server (if not already running):**

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

**Step 2 — Add videos to the queue:**

```bash
curl -X POST http://localhost:8000/transcription/add_to_queue/ \
  -F "source=https://www.youtube.com/watch?v=VIDEO_ID" \
  -F "loc=tabconf" \
  -F "username=your_name" \
  -F "deepgram=true" \
  -F "diarize=true" \
  -F "markdown=true" \
  -F "correct=true" \
  -F "summarize=true" \
  -F "llm_provider=google"
```

Queue multiple videos at once:

```bash
VIDEO_IDS=("id1" "id2" "id3")
for id in "${VIDEO_IDS[@]}"; do
  curl -X POST http://localhost:8000/transcription/add_to_queue/ \
    -F "source=https://www.youtube.com/watch?v=${id}" \
    -F "loc=tabconf" \
    -F "username=your_name" \
    -F "deepgram=true" \
    -F "diarize=true" \
    -F "correct=true"
done
```

**Step 3 — Check the queue:**

```bash
curl http://localhost:8000/transcription/queue/
```

**Step 4 — Start processing:**

```bash
curl -X POST http://localhost:8000/transcription/start/
```

**Step 5 — Verify results:**

```bash
# All transcripts in DB
curl http://localhost:8000/transcription/db/transcripts/

# Single transcript by ID
curl http://localhost:8000/transcription/db/transcripts/<transcript_uuid>

# Corrected transcripts
curl http://localhost:8000/transcription/db/corrected/

# Summaries
curl http://localhost:8000/transcription/db/summaries/
```

---

## Pipeline 2 — Automated Ingestion Pipeline

**What it does:** Continuously monitors YouTube channels → discovers new videos → classifies them (technical vs. non-technical) with Gemini LLM → queues approved videos for transcription automatically.

```
youtube_channels (DB)
       │
  [ChannelScanner] ──▶ YouTube Data API v3, discover new videos
       │
  [ContentClassifier] ──▶ Gemini LLM, filter technical content
       │
  [IngestionService] ──▶ Queue approved videos → Pipeline 1
```

### 2A. Seed content sources

Register the YouTube channels you want to monitor. Either use the seed script:

```bash
python -m scripts.seed_channels
```

Or add channels manually via the API:

```bash
curl -X POST http://localhost:8000/ingestion/sources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bitcoin Magazine",
    "slug": "bitcoin-magazine",
    "source_type": "youtube",
    "base_url": "https://www.youtube.com/@BitcoinMagazine",
    "config": {
      "yt_channel_id": "UCpXY...",
      "priority": 1,
      "category": "conference"
    },
    "is_active": true
  }'
```

Verify channels are registered:

```bash
curl http://localhost:8000/ingestion/sources
```

### 2B. Scan → Classify → Queue (individually)

Run each stage separately when you want fine-grained control or want to review classifications before queuing.

**Step 1 — Scan all channels for new videos:**

```bash
curl -X POST http://localhost:8000/ingestion/scan
```

Response:
```json
{ "status": "success", "items_discovered": 12, "errors": [] }
```

Scan a specific channel only:
```bash
curl -X POST http://localhost:8000/ingestion/scan/<source_uuid>
```

**Step 2 — Review discovered items (before classification):**

```bash
# All discovered items
curl "http://localhost:8000/ingestion/items?status=discovered"

# Filter to a specific source
curl "http://localhost:8000/ingestion/items?source_id=<source_uuid>&limit=20"
```

**Step 3 — Classify pending items with Gemini LLM:**

```bash
curl -X POST http://localhost:8000/ingestion/classify
```

Response:
```json
{
  "status": "success",
  "items_classified": 10,
  "items_approved": 7,
  "items_rejected": 3,
  "errors": []
}
```

Classify a single item manually:
```bash
curl -X POST http://localhost:8000/ingestion/classify/<item_uuid>
```

**Step 4 — Review classifications, override if needed:**

```bash
# See approved (technical) items
curl "http://localhost:8000/ingestion/items?is_technical=true"

# See rejected items
curl "http://localhost:8000/ingestion/items?is_technical=false"

# Manually approve a rejected item
curl -X PUT http://localhost:8000/ingestion/items/<item_uuid> \
  -H "Content-Type: application/json" \
  -d '{"is_technical": true, "classification_reason": "Manually approved — conference keynote."}'

# Manually reject an approved item
curl -X PUT http://localhost:8000/ingestion/items/<item_uuid> \
  -H "Content-Type: application/json" \
  -d '{"is_technical": false, "classification_reason": "Off-topic."}'
```

**Step 5 — Queue approved items for transcription:**

```bash
curl -X POST http://localhost:8000/ingestion/queue
```

Response:
```json
{ "status": "success", "items_queued": 7, "errors": [] }
```

**Step 6 — Start transcription:**

```bash
curl -X POST http://localhost:8000/transcription/start/
```

### 2C. Scan → Classify → Queue (one shot)

Run the entire ingestion pipeline in a single call:

```bash
curl -X POST http://localhost:8000/ingestion/run
```

Response:
```json
{
  "status": "success",
  "scan":     { "items_discovered": 5, "errors": [] },
  "classify": { "items_classified": 5, "items_approved": 3, "items_rejected": 2, "errors": [] },
  "queue":    { "items_queued": 3, "errors": [] }
}
```

Then start transcription:

```bash
curl -X POST http://localhost:8000/transcription/start/
```

### 2D. Start transcription on queued items

After either 2B or 2C, kick off transcription:

```bash
curl -X POST http://localhost:8000/transcription/start/
```

Check audit logs:

```bash
curl "http://localhost:8000/ingestion/runs?limit=10"
```

---

## Pipeline 3 — Audiobook Pipeline

**What it does:** Takes plain `.txt` files (articles, guides, transcripts) → cleans text → LLM chapterization (optional) → TTS synthesis (Deepgram or SmallestAI) → stitches MP3 → uploads to Supabase Storage (optional) → saves episode + playlist records to DB.

```
.txt files on disk
       │
  [Ingestion] ──▶ Parse YAML frontmatter → InputFile dataclasses
       │
  [Routing] ──▶ single_article OR series group
       │
  [Text Cleaning] ──▶ Strip timestamps, stage directions, whitespace
       │
  [LLM Rewrite] ──▶ GPT-4.1: split into chapters (skipped for short/series)
       │
  [Normalize + Chunk] ──▶ Expand $1.5M → "1.5 million dollars", split by char limit
       │
  [TTS Synthesis] ──▶ Deepgram / SmallestAI → cached .mp3 chunks
       │
  [Audio Stitching] ──▶ pydub: concat chunks → chapters → final episode.mp3
       │
  [Storage Upload] ──▶ Supabase CDN (optional)
       │
  [DB Persistence] ──▶ audio_episodes + audio_playlists tables
```

### 3A. Prepare input files

Create the input directory:

```bash
mkdir -p input/audiobooks
```

**Option 1 — Single article** (place in `input/audiobooks/`):

```text
---
type: single_article
title: "Bitcoin Mining Economics in 2025"
author: "Lyn Alden"
source_url: "https://example.com/article"
tags: ["mining", "economics"]
description: "A deep dive into mining profitability."
---

The actual article text goes here. Can be thousands of words.
```

**Option 2 — Series (multi-part guide):**

Create one `.txt` file per episode, all sharing the same `series_slug`:

`input/audiobooks/lmab-01.txt`:
```text
---
type: series
series_slug: learn-me-a-bitcoin
series_title: "Learn Me a Bitcoin"
sequence_number: 1
title: "What is Bitcoin?"
author: Greg Walker
source_url: https://learnmeabitcoin.com/beginners/
tags: ["bitcoin", "basics"]
---
Bitcoin is a decentralized...
```

`input/audiobooks/lmab-02.txt`:
```text
---
type: series
series_slug: learn-me-a-bitcoin
series_title: "Learn Me a Bitcoin"
sequence_number: 2
title: "Transactions Explained"
author: Greg Walker
source_url: https://learnmeabitcoin.com/beginners/transactions
tags: ["bitcoin", "transactions"]
---
A transaction is...
```

> **YAML gotcha:** If `series_title` contains a colon (e.g. `Learn Me a Bitcoin: Networking`), wrap it in double quotes, otherwise YAML will reject it.

**Option 3 — Plain text (no frontmatter):**

```text
Bitcoin is a decentralized peer-to-peer electronic cash system...
```

The filename (minus extension, dashes/underscores replaced with spaces, title-cased) becomes the episode title.

### 3B. Run the audiobook curator

Create a runner script `run_curator.py`:

```python
from app.services.audiobook.curator import AudiobookCurator

curator = AudiobookCurator()
result = curator.curate_from_directory("input/audiobooks")
print(result)
# {'episodes_generated': 9, 'playlists_touched': 1, 'errors': [], 'success': True}
```

Run it:

```bash
python run_curator.py
```

**Common override options:**

```python
# Skip the OpenAI LLM rewrite step (faster + cheaper for short content)
curator = AudiobookCurator(skip_llm=True)

# Use SmallestAI instead of Deepgram for TTS
curator = AudiobookCurator(provider_override="smallest")

# Enable multi-speaker diarization (for podcasts/interviews)
curator = AudiobookCurator(diarize=True)

# Lower threshold: run LLM chapterization on articles ≥ 3,000 words (default: 5,000)
curator = AudiobookCurator(chapterize_threshold=3000)

# Process only a subfolder (faster iteration, skips unrelated files)
curator.curate_from_directory("input/audiobooks/networking")

# All overrides combined
curator = AudiobookCurator(
    skip_llm=True,
    provider_override="smallest",
    diarize=True,
    chapterize_threshold=3000,
)
```

**Expected output after a successful run:**

```
============================================================
  Results
============================================================
  Episodes generated : 9
  Playlists touched  : 1
  Errors             : 0

  ✅ Pipeline completed successfully!
```

**Output locations:**

| Location | What |
|---|---|
| `outputs/audiobooks/<episode-id>/` | Per-episode MP3 + per-chapter MP3s |
| `.cache/audiobooks/` | TTS chunk cache (re-runs are free for unchanged chunks) |
| DB `audio_episodes` | `audio_url`, `duration_seconds`, `chapters` JSON, `status = "completed"` |
| DB `audio_playlists` | Playlist title, slug, episode count, total duration |
| Supabase Storage | Public CDN URL (only if `SUPABASE_URL` + `SUPABASE_KEY` are set) |

> **Re-run safety:** The pipeline is **idempotent**. Episodes with `status = "completed"` are skipped automatically. Episodes with `status = "failed"` or `"pending"` are retried.

**Quick one-off generation (no DB):**

```python
from app.services.audiobook.pipeline import AudiobookService

service = AudiobookService()
with open("input/audiobooks/some-article.txt") as f:
    text = f.read()

result = service.generate_from_text(text, skip_llm=True, title="some-article")
print("Saved to:", result["audio_url"])
```

### 3C. Query generated playlists via API

After the pipeline runs, query the results via the FastAPI server:

```bash
# List all playlists
curl http://localhost:8000/audiobooks/playlists

# Filter by type
curl "http://localhost:8000/audiobooks/playlists?playlist_type=series"
curl "http://localhost:8000/audiobooks/playlists?playlist_type=collection"

# Get a single playlist with all episodes
curl http://localhost:8000/audiobooks/playlists/learn-me-a-bitcoin

# Get a single episode by UUID
curl http://localhost:8000/audiobooks/episodes/<episode_uuid>
```

---

## Quick Reference — All Commands End-to-End

Copy-paste these in order for a complete first run.

```bash
# ── SETUP ──────────────────────────────────────────────────────────────────
git clone https://github.com/staru09/transcription_engine.git && cd transcription_engine
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
sudo apt install ffmpeg                  # or brew install ffmpeg on macOS
cp env.example .env                      # fill in your keys
docker compose up -d postgres            # start local postgres
tstbtc db init                           # create transcription tables
python scripts/migrate_schema.py         # create audiobook tables
tstbtc db check                          # verify DB connectivity

# ── SERVER ────────────────────────────────────────────────────────────────
python -m uvicorn server:app --host 0.0.0.0 --port 8000 &
# (or let the CLI auto-start it)

# ── PIPELINE 1: Transcription (single video via CLI) ─────────────────────
tstbtc transcribe "https://www.youtube.com/watch?v=VIDEO_ID" \
  --deepgram --diarize --markdown --correct --summarize \
  --llm-provider google --loc "tabconf" --username "your_name"

# ── PIPELINE 2: Ingestion (automated channel pipeline) ────────────────────
python -m scripts.seed_channels                         # register channels
curl -X POST http://localhost:8000/ingestion/run        # scan+classify+queue
curl -X POST http://localhost:8000/transcription/start/ # transcribe queued

# ── PIPELINE 3: Audiobook (txt → MP3) ────────────────────────────────────
mkdir -p input/audiobooks
# ... place your .txt files in input/audiobooks/ ...
python - <<'EOF'
from app.services.audiobook.curator import AudiobookCurator
result = AudiobookCurator(skip_llm=True).curate_from_directory("input/audiobooks")
print(result)
EOF

# ── VERIFY RESULTS ────────────────────────────────────────────────────────
curl http://localhost:8000/transcription/db/transcripts/
curl http://localhost:8000/audiobooks/playlists
```

---

## Configuration Reference

### `config.ini` — Transcription pipeline defaults

```ini
[DEFAULT]
deepgram = True                         # Use Deepgram by default
diarize = True                          # Enable speaker diarization
summarize = False                       # Disable summarization by default
github = False                          # Don't push to GitHub
save_to_markdown = True                 # Save transcript as Markdown
needs_review = False
one_sentence_per_line = True
llm_provider = openai                   # openai | google
llm_correction_model = gpt-4o          # Model for LLM correction pass
llm_summary_model = gpt-4o             # Model for summarization

[development]
verbose_logging = True
server_mode = dev
server_verbose = True
```

### `app/services/audiobook_config.yaml` — Audiobook pipeline defaults

```yaml
llm:
  provider: openai
  model: gpt-4.1                        # Chapterization model
  temperature: 0.3
  max_words_per_request: 3000           # Splits long articles before LLM call

tts:
  provider: deepgram                    # deepgram | smallest
  voices:
    deepgram: aura-2-thalia-en
    smallest: meher
  models:
    smallest: lightning_v3.1_pro
  max_chars:
    deepgram: 1900                      # Per-request character limit
    smallest: 240
  speed: 1.0
  format: mp3

audio:
  silence_ms_between_chunks: 220       # Gap between TTS chunks within a chapter
  silence_ms_between_chapters: 700     # Gap between chapters in the final file
  target_dbfs: -20.0                   # Loudness normalization target

paths:
  output_dir: outputs/audiobooks
  cache_dir: .cache/audiobooks
  lexicon: audiobook_lexicon.json      # Domain-specific pronunciation overrides
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No module named uvicorn` | Run `pip install -r requirements.txt` inside your venv |
| `ImportError: cannot import name 'genai' from 'google'` | Reinstall: `pip install google-genai` |
| `DATABASE_URL not set` | Ensure `.env` exists with the correct `DATABASE_URL` |
| `Network is unreachable` (Supabase DB) | Use the Supabase **pooler** connection string and add `sslmode=require` |
| `ffmpeg not found` | Install ffmpeg and ensure it's on your `PATH` |
| `TTS 401 / 403` errors | Check `DEEPGRAM_API_KEY` or `SMALLEST_API_KEY` in `.env` |
| `mapping values are not allowed` YAML error | Wrap the value containing `:` in double quotes in your `.txt` frontmatter |
| Episode stuck in `generating` | A previous run crashed mid-way. Re-run — completed episodes are skipped automatically |
| `context canceled` in terminal | Run was interrupted. Re-run — completed episodes are skipped |
| Provider switch has no effect | Run `tstbtc server stop` before switching STT provider — the server caches the provider |
| `Method Not Allowed` on `/transcription/start/` | Use `POST`, not `GET` |
| LLM returns empty chapters | Fallback kicks in automatically — article is converted as a single chapter |
| `IntegrityError` on re-run | Safe to ignore — optimistic concurrency handles duplicate playlist/episode creation |
