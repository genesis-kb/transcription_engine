# Bitcoin Transcription Engine

A transcription pipeline for Bitcoin conference talks, podcasts, and technical content. Ingests YouTube videos, transcribes audio via multiple STT providers, corrects transcripts with LLM, extracts metadata, generates summaries, and stores everything in PostgreSQL.

## Architecture

```
YouTube Video URL
       |
  [Preprocess] --> Download video, extract audio (FFmpeg)
       |
  [Transcribe] --> STT (Whisper / Deepgram / SmallestAI)
       |
  [Metadata Extraction] --> Gemini LLM (speakers, conference, topics)
       |
  [Correction] --> Gemini LLM (fix ASR errors, technical terms)
       |
  [Summarization] --> Gemini LLM (structured summary)
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

## LLM Services (Gemini)

All LLM services use `google-genai` SDK with `gemini-3-flash-preview` and include retry logic with exponential backoff for 503/429 errors.

| Service | Purpose | Chunk Size |
|---------|---------|------------|
| **MetadataExtractor** | Extract speakers, conference, topics from video metadata | Single call |
| **CorrectionService** | Fix ASR errors, technical terminology | 5000 chars/chunk |
| **SummarizerService** | Generate structured summaries | 30000 chars/chunk |
| **ContentClassifier** | Classify videos as technical/non-technical | Single call |

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

### Prerequisites

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
# Clone the repo
git clone https://github.com/staru09/transcription_engine.git
cd transcription_engine

# Create venv and install deps
uv venv
uv pip install -r requirements.txt

# Or with pip
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

### Configuration

```bash
cp env.example .env
```

Required environment variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (AWS RDS) |
| `GOOGLE_API_KEY` | Gemini API for correction, summarization, classification, metadata extraction |
| `YOUTUBE_API_KEY` | YouTube Data API v3 for channel scanning |
| `DEEPGRAM_API_KEY` | Deepgram STT (if using Deepgram) |
| `SMALLEST_API_KEY` | SmallestAI STT (if using SmallestAI) |

Optional:

| Variable | Purpose |
|----------|---------|
| `TRANSCRIPTION_SERVER_URL` | Override transcription server URL (default: `http://localhost:8000`) |

Pipeline settings are in `config.ini`:

```ini
[DEFAULT]
deepgram = True
diarize = True
summarize = False
llm_provider = google
llm_correction_model = gemini-3-flash-preview
llm_summary_model = gemini-3-flash-preview
smallestai = False
classification_model = gemini-3-flash-preview
classification_min_duration = 600
classification_max_duration = 3000
```

## Usage

### Start the Server

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### Transcribe a YouTube Video

Queue a video via the API:

```bash
curl -X POST http://localhost:8000/transcription/add_to_queue/ \
  -F "source=https://www.youtube.com/watch?v=VIDEO_ID" \
  -F "loc=tabconf" \
  -F "username=your_username" \
  -F "smallestai=true" \
  -F "diarize=true" \
  -F "markdown=true" \
  -F "correct=true" \
  -F "summarize=true" \
  -F "llm_provider=google"
```

Start processing:

```bash
curl -X POST http://localhost:8000/transcription/start/
```

Check queue status:

```bash
curl http://localhost:8000/transcription/queue/
```

### Channel Scanner (Automated Ingestion)

Scan a YouTube channel for new videos, classify them, and queue for transcription:

```bash
# Seed channels
python -m scripts.seed_channels

# Scan, classify, and queue via API
curl -X POST http://localhost:8000/ingestion/scan
curl -X POST http://localhost:8000/ingestion/classify
curl -X POST http://localhost:8000/ingestion/queue
```

## API Endpoints

### Transcription

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/transcription/add_to_queue/` | Add a video to the transcription queue |
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
| POST | `/ingestion/scan` | Scan channels for new videos |
| POST | `/ingestion/classify` | Classify pending videos |
| POST | `/ingestion/queue` | Queue approved videos |

## Project Structure

```
app/
  config.py              # Settings, env vars, config.ini
  transcript.py          # Transcript data model
  transcription.py       # Pipeline orchestrator
  media_processor.py     # Audio/video download and conversion
  services/
    correction.py        # LLM transcript correction (Gemini)
    summarizer.py        # LLM summarization (Gemini)
    metadata_extractor.py # LLM metadata extraction (Gemini)
    content_classifier.py # LLM content classification (Gemini)
    channel_scanner.py   # YouTube channel scanning
    ingestion_service.py # Automated ingestion pipeline
    database_service.py  # SQLAlchemy ORM for PostgreSQL
    smallestai.py        # SmallestAI STT provider
    deepgram.py          # Deepgram STT provider
routes/
  transcription.py       # Transcription API routes
  ingestion.py           # Ingestion API routes
scripts/
  scan_tabconf.py        # Standalone channel scanner
  generate_audio.py      # TTS audio generation
  seed_channels.py       # Seed YouTube channels in DB
server.py                # FastAPI app entry point
config.ini               # Pipeline configuration
```

Contributors can join our [discord](https://discord.gg/BxqCaQHFGz) server here

## Acknowledgements

This project is a fork of [tstbtc](https://github.com/bitcointranscripts/tstbtc), built by the [Bitcoin Transcripts](https://github.com/bitcointranscripts) team. Their work on creating an open-source transcription pipeline for Bitcoin technical content made this project possible. We've extended the original engine with LLM-powered operations but the core transcription architecture and the vision of making Bitcoin knowledge accessible to everyone comes from their efforts. Thank you to the Bitcoin Transcripts contributors for building and maintaining this foundation.

## License

MIT License. See [LICENSE](LICENSE).
