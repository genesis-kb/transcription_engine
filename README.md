# Bitcoin Transcription Engine

A transcription pipeline for Bitcoin conference talks, podcasts, and technical content. Ingests YouTube videos, transcribes audio via multiple STT providers, corrects transcripts with LLM, extracts metadata, generates summaries, and stores everything in PostgreSQL.

## Architecture

```
YouTube Video URL
       |
  [Preprocess] --> Download video, extract audio (FFmpeg)
       |
  [Transcribe] --> STT (Whisper / Deepgram / SmallestAI / VibeVoice)
       |
  [Metadata Extraction] --> Gemma via Ollama (speakers, conference, topics)
       |
  [Correction] --> LLM: Gemini / OpenAI / Gemma (fix ASR errors, technical terms)
       |
  [Summarization] --> LLM: Gemini / OpenAI / Gemma (structured summary)
       |
  [Postprocess] --> Export to Markdown, save to PostgreSQL
```

### Automated Ingestion Pipeline

```
youtube_channels (DB)
       |
  [ChannelScanner] --> YouTube Data API v3, discover new videos
       |
  [ContentClassifier] --> Gemini LLM, filter technical content
       |
  [IngestionService] --> Queue approved videos for transcription
```

## STT Providers

| Provider | Type | Best For |
|----------|------|----------|
| **Whisper** | Local (OpenAI) | Offline, privacy-sensitive |
| **Deepgram** | Cloud API | Fast, accurate, diarization |
| **SmallestAI** | Cloud API | Multi-speaker, emotion detection |
| **VibeVoice** | Open-source | SOTA performance, privacy-focused |

Whisper and VibeVoice need optional extras (see [Installation](#installation)). VibeVoice is only available once its dependencies are installed.

## LLM Services

| Service | Purpose | Backend | Chunk Size |
|---------|---------|---------|------------|
| **MetadataExtractor** | Extract speakers, conference, topics from video metadata | Gemma via [Ollama](https://ollama.com) (`GEMMA_MODEL`, default `gemma3:4b`) | Single call |
| **CorrectionService** | Fix ASR errors, technical terminology | `llm_provider`: `google` (Gemini), `openai` or `gemma` | 5000 chars/chunk |
| **SummarizerService** | Generate structured summaries | `llm_provider`: `google` (Gemini), `openai` or `gemma` | 30000 chars/chunk |
| **ContentClassifier** | Classify videos as technical/non-technical | Gemini (`google-genai`) | Single call |

Metadata extraction is optional: if Ollama isn't running, it is skipped with a warning and the existing metadata is kept. To enable it, install Ollama and pull the model (`ollama pull gemma3:4b`).

## Tech Stack

- **Backend**: FastAPI (Python)
- **Database**: AWS RDS PostgreSQL
- **Deployment**: AWS EC2 (t3.small)
- **Frontend**: React + TypeScript + Vite (separate repo)
- **Frontend Backend**: Express.js (reads from RDS)
- **Frontend Hosting**: GitHub Pages
- **HTTPS**: Cloudflare Tunnel
- **Linting**: Ruff

## Setup

Quick runbook for local startup, DB initialization, and queuing 10 videos:
- [docs/local-run-and-queue.md](docs/local-run-and-queue.md)

### Prerequisites

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
# Clone the repo
git clone https://github.com/genesis-kb/transcription_engine.git
cd transcription_engine

# Create venv and install the project (this also installs the `tstbtc` CLI)
uv venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
uv pip install -e .

# Or with pip
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -e .
```

Installing with `-e .` (rather than only `-r requirements.txt`) is what creates the `tstbtc` command. The venv must be activated in every new terminal for `tstbtc` to be found.

Optional STT extras (both pull in PyTorch):

```bash
pip install -e ".[whisper]"     # Whisper (local)
pip install -e ".[vibevoice]"   # VibeVoice (also set HF_TOKEN to download the model)
```

### Configuration

```bash
cp env.example .env
cp config.ini.example config.ini
```

Required environment variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (local Docker or AWS RDS) |
| `GOOGLE_API_KEY` | Gemini, used by content classification and when `llm_provider = google` |
| `OPENAI_API_KEY` | OpenAI, when `llm_provider = openai` (the default in `config.ini.example`) |
| `YOUTUBE_API_KEY` | YouTube Data API v3 for channel scanning |
| `DEEPGRAM_API_KEY` | Deepgram STT (if using Deepgram) |
| `SMALLEST_API_KEY` | SmallestAI STT (if using SmallestAI) |

Optional:

| Variable | Purpose |
|----------|---------|
| `TRANSCRIPTION_SERVER_URL` | Override transcription server URL (default: `http://localhost:8000`) |
| `GEMMA_MODEL` | Ollama model for metadata extraction and `llm_provider = gemma` (default: `gemma3:4b`) |
| `HF_TOKEN` | HuggingFace token for downloading the VibeVoice model |
| `SARVAM_API_KEY` | Sarvam AI, for `tstbtc translate` |

### Database

You can run PostgreSQL either locally via Docker or against AWS RDS. The app picks whichever `DATABASE_URL` points at.

**Option A — Local PostgreSQL via Docker** (no AWS needed):

```bash
# Start just the postgres container
docker compose up -d postgres

# Point the app at it (already the default in env.example)
# DATABASE_URL=postgresql+psycopg2://bitcoin:bitcoin@127.0.0.1:5434/transcription_engine

# Create the schema
tstbtc db init
```

The container is exposed on host port **5434** (see `docker-compose.yml`). On Windows/macOS, Docker Desktop must be running before `docker compose` will work. Data persists in the `postgres_data` Docker volume. To wipe it: `docker compose down -v`.

**Option B — AWS RDS** (or any remote Postgres):

Set `DATABASE_URL` in `.env` to your RDS connection string, then run `tstbtc db init` once to create tables.

**Use the `postgresql+psycopg2://` scheme.** The project installs the `psycopg2-binary` driver. SQLAlchemy 2.1+ maps a bare `postgresql://` URL to the newer `psycopg` (v3) driver instead, which fails with `ModuleNotFoundError: No module named 'psycopg'`.

Check connectivity anytime with `tstbtc db check`.

### Pipeline settings

Pipeline settings are in `config.ini` (copied from `config.ini.example`). The main keys:

```ini
[DEFAULT]
# whisper | deepgram | smallestai | vibevoice
asr_provider = whisper
diarize = True
summarize = False
# google | openai | gemma
llm_provider = openai
llm_correction_model = gpt-4o
llm_summary_model = gpt-4o
# Only used when asr_provider = vibevoice
vibevoice_chunk_length = 180
# Ingestion classification (Gemini)
classification_model = gemini-3-flash-preview
classification_min_duration = 600
classification_max_duration = 3000
```

`asr_provider` and `llm_provider` are the defaults for the `--asr-provider` and `--llm-provider` CLI flags. To use Gemini, set `llm_provider = google` and `llm_correction_model` / `llm_summary_model = gemini-3-flash-preview`. Keep comments on their own lines: `config.ini` does not support comments after a value.

## Usage

The project provides both a CLI (`tstbtc` / `transcriber.py`) and an HTTP API. The CLI auto-starts the server in the background, so for most workflows you only need the CLI.

### CLI (recommended)

Transcribe a YouTube video with Deepgram:

```bash
tstbtc transcribe "https://www.youtube.com/watch?v=VIDEO_ID" \
  --asr-provider deepgram \
  --diarize \
  --markdown \
  --summarize \
  --correct \
  --llm-provider google \
  --loc "tabconf" \
  --username "your_name"
```

With SmallestAI instead:

```bash
tstbtc transcribe "https://www.youtube.com/watch?v=VIDEO_ID" \
  --asr-provider smallestai \
  --diarize \
  --markdown \
  --summarize \
  --correct \
  --llm-provider google \
  --loc "tabconf" \
  --username "your_name"
```

With VibeVoice (needs `pip install -e ".[vibevoice]"` and `HF_TOKEN`):

```bash
tstbtc transcribe "https://www.youtube.com/watch?v=VIDEO_ID" \
  --asr-provider vibevoice \
  --diarize \
  --markdown \
  --summarize \
  --correct \
  --llm-provider google \
  --loc "tabconf" \
  --username "your_name"
```

With Whisper (local, no cloud STT key required; needs `pip install -e ".[whisper]"`):

```bash
tstbtc transcribe "https://www.youtube.com/watch?v=VIDEO_ID" \
  --asr-provider whisper \
  --markdown \
  --username "your_name"
```

If `--asr-provider` is omitted, `asr_provider` from `config.ini` is used. `--llm-provider` accepts `google`, `openai` or `gemma`. The CLI also lists `claude`, but correction and summarization don't support it yet.

Other useful commands:

```bash
# Server management
tstbtc server start              # start FastAPI server in background
tstbtc server status             # check if running
tstbtc server stop               # stop (required before switching STT provider)
tstbtc server logs --follow      # tail logs live

# Transcribe a local audio file
tstbtc transcribe "/path/to/file.mp3" --asr-provider deepgram --title "Talk title" --username "your_name"

# See all flags
tstbtc transcribe --help
```

**Note on switching services:** the server caches the transcription service (Deepgram/Whisper/SmallestAI/VibeVoice) after the first request. To switch between them, run `tstbtc server stop` before the next transcription.

Output locations:

| What | Where |
|------|-------|
| Markdown transcript | `local_models/<loc>/<slug>.md` |
| Raw STT output + metadata | `metadata/<loc>/<slug>/` |
| Database row | `transcripts` table (local Postgres or AWS RDS) |

### HTTP API (advanced)

If you want to call the server directly (e.g. from another service):

```bash
# Start the server manually
python -m uvicorn server:app --host 0.0.0.0 --port 8000

# Queue a video
curl -X POST http://localhost:8000/transcription/add_to_queue/ \
  -F "source=https://www.youtube.com/watch?v=VIDEO_ID" \
  -F "loc=tabconf" \
  -F "username=your_username" \
  -F "asr_provider=smallestai" \
  -F "diarize=true" \
  -F "markdown=true" \
  -F "correct=true" \
  -F "summarize=true" \
  -F "llm_provider=google"

# Start processing
curl -X POST http://localhost:8000/transcription/start/

# Check queue status
curl http://localhost:8000/transcription/queue/
```

### Channel Scanner (Automated Ingestion)

Scan a YouTube channel for new videos, classify them, and queue for transcription. The `tstbtc ingest` commands call the server's HTTP API and do not start it automatically, so start the server first:

```bash
tstbtc server start

# Add a source (e.g. a YouTube channel) to monitor
tstbtc ingest sources add SOURCE_ID "Source name" --category conference --priority 2
tstbtc ingest sources list

# Run the full pipeline (scan → classify → queue approved items)
tstbtc ingest run
# or via the API:
curl -X POST http://localhost:8000/ingestion/run
```

The stages can also be run individually with `tstbtc ingest scan` and `tstbtc ingest classify` (or `POST /ingestion/scan` and `POST /ingestion/classify`), and results reviewed with `tstbtc ingest items list` and `tstbtc ingest items approve|reject ITEM_ID`. Queueing approved items for transcription only happens in `run`, which scans and classifies again, so running `scan` and `classify` right before it repeats that work and uses extra YouTube API quota.

## API Endpoints

### Transcription

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/transcription/preprocess/` | Preprocess a source (fetch metadata) without transcribing |
| POST | `/transcription/add_to_queue/` | Add a video to the transcription queue |
| POST | `/transcription/remove_from_queue/` | Remove a source from the queue |
| POST | `/transcription/start/` | Start processing the queue |
| GET | `/transcription/queue/` | View current queue status |
| GET | `/transcription/corrected/` | Get corrected transcripts |
| GET | `/transcription/summaries/` | Get summaries |

### Database (PostgreSQL)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/transcription/db/transcripts/` | All transcripts from DB |
| GET | `/transcription/db/transcripts/{id}` | Single transcript by ID |
| GET | `/transcription/db/corrected/` | Corrected transcripts from DB |
| GET | `/transcription/db/summaries/` | Summaries from DB |

### Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ingestion/run` | Run the full pipeline: scan → classify → queue |
| POST | `/ingestion/scan` | Scan all active sources for new items |
| POST | `/ingestion/scan/{source_id}` | Scan a single source |
| POST | `/ingestion/classify` | Classify pending items |
| POST | `/ingestion/classify/{item_id}` | Classify a single item |
| GET | `/ingestion/sources` | List monitored sources |
| POST | `/ingestion/sources` | Add a source |
| PUT | `/ingestion/sources/{source_id}` | Update a source |
| DELETE | `/ingestion/sources/{source_id}` | Remove a source |
| GET | `/ingestion/items` | List discovered items |
| PUT | `/ingestion/items/{item_id}` | Update an item (e.g. approve/reject) |
| GET | `/ingestion/runs` | List past ingestion runs |

### Audiobooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/audiobooks/playlists` | List audiobook playlists |
| GET | `/audiobooks/playlists/{slug}` | Get a playlist |
| GET | `/audiobooks/episodes/{episode_id}` | Get an episode |

### Curator and Media

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/curator/get_sources/` | Get sources for a location |
| POST | `/curator/get_transcription_backlog/` | Get the transcription backlog |
| POST | `/media/youtube-video-url` | Extract the direct video URL from a YouTube link |

## Project Structure

```
app/
  config.py              # Settings, env vars, config.ini
  database.py            # SQLAlchemy engine/session setup
  models.py              # ORM models (content sources/items, transcripts, speakers, runs)
  transcript.py          # Transcript data model
  transcription.py       # Pipeline orchestrator
  media_processor.py     # Audio/video download and conversion
  exporters.py           # Markdown / JSON / text exporters
  commands/              # CLI command groups (db, server, ingest, media, curator)
  exceptions/            # Structured exception types
  services/
    correction.py        # LLM transcript correction
    summarizer.py        # LLM summarization
    metadata_extractor.py # Metadata extraction (Gemma via Ollama)
    content_classifier.py # Content classification (Gemini)
    global_tag_manager.py # Global tag/terminology dictionary used by correction
    channel_scanner.py   # YouTube channel scanning
    ingestion_service.py # Automated ingestion pipeline
    database_service.py  # Database access layer
    factory.py           # ASR provider discovery/registry
    audiobook_service.py # Audiobook pipeline entry point
    audiobook/           # Audiobook pipeline (TTS, stitching, playlists)
    translation/         # Translation pipeline (`tstbtc translate`)
    providers/
      deepgram.py        # Deepgram STT provider
      smallestai.py      # SmallestAI STT provider
      whisper.py         # Whisper (local) STT provider
      vibevoice.py       # VibeVoice STT provider
routes/
  transcription.py       # Transcription API routes
  ingestion.py           # Ingestion API routes
  audiobooks.py          # Audiobook API routes
  curator.py             # Curator API routes
  media.py               # Media API routes
  translation.py         # Translation API routes
scripts/
  migrate_schema.py      # Database schema migration
  add_indexes.py         # Database index creation
  check_diff.sh          # Helper for reviewing bitcointranscripts PRs (inherited from tstbtc)
docs/                    # Runbooks and pipeline guides
server.py                # FastAPI app entry point
transcriber.py           # `tstbtc` CLI entry point
config.ini.example       # Pipeline configuration template (copy to config.ini)
env.example              # Environment variables template (copy to .env)
```

Contributors can join our [discord](https://discord.gg/BxqCaQHFGz) server here

## Acknowledgements

This project is a fork of [tstbtc](https://github.com/bitcointranscripts/tstbtc), built by the [Bitcoin Transcripts](https://github.com/bitcointranscripts) team. Their work on creating an open-source transcription pipeline for Bitcoin technical content made this project possible. We've extended the original engine with LLM-powered operations but the core transcription architecture and the vision of making Bitcoin knowledge accessible to everyone comes from their efforts. Thank you to the Bitcoin Transcripts contributors for building and maintaining this foundation.

## License

MIT License. See [LICENSE](LICENSE).
