# Audiobook Pipeline — How to Run

This guide covers everything you need to go from a `.txt` file to a playable audio episode in the database.

---

## Prerequisites

### 1. System dependency — `ffmpeg`

`pydub` (the audio stitching library) requires `ffmpeg` on the system `PATH`:

```bash
# Ubuntu / Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
winget install Gyan.FFmpeg
```

### 2. Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment variables

Copy the example and fill in your keys:

```bash
cp env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | ✅ Always | PostgreSQL connection string |
| `OPENAI_API_KEY` | ✅ if LLM rewrite is on | GPT-4.1 for chapterization |
| `DEEPGRAM_API_KEY` | ✅ if using Deepgram | TTS synthesis |
| `SMALLEST_API_KEY` | ✅ if using Smallest AI | TTS synthesis |
| `SUPABASE_URL` | Optional | Upload audio to Supabase Storage |
| `SUPABASE_KEY` | Optional | Supabase service-role key |

> **Note:** `OPENAI_API_KEY` is only needed if you run without `--skip-llm`. If you skip LLM, only the active TTS key is required.

### 4. Database tables

Ensure the `audio_playlists` and `audio_episodes` tables exist:

```bash
python scripts/migrate_schema.py
```

---

## Preparing Input Files

Place `.txt` files under `input/audiobooks/` (or a subdirectory — the pipeline accepts any directory path).

### Single article

```text
---
type: single_article
title: "Bitcoin Mining Economics in 2025"
author: "Lyn Alden"
source_url: "https://example.com/article"
tags: ["mining", "economics"]
description: "A deep dive into mining profitability."
---
The actual article text goes here...
```

### Series (multi-part guide)

Each episode is a **separate file**. Files are grouped by `series_slug` and ordered by `sequence_number`:

```text
---
type: series
series_slug: learn-me-a-bitcoin
series_title: Learn Me a Bitcoin
sequence_number: 3
title: Mining and Proof of Work
author: Greg Walker
source_url: https://learnmeabitcoin.com/beginners/mining
tags: ["bitcoin", "mining"]
description: How Bitcoin mining works.
---
Mining is the process by which...
```

> **YAML gotcha:** If your `series_title` contains a colon (e.g. `"Learn Me a Bitcoin: Networking"`), wrap the whole value in quotes, otherwise YAML will reject it.

### Plain text (no frontmatter)

Files with no `---` block are automatically treated as a single article. The filename (minus extension, dashes/underscores replaced with spaces) becomes the title.

---

## Running the Pipeline

### Full pipeline (recommended)

Create a Python script (e.g., `run_curator.py`) to curate a whole directory:

```python
from app.services.audiobook.curator import AudiobookCurator

curator = AudiobookCurator()
curator.curate_from_directory("input/audiobooks")
```

### Common overrides

You can override defaults by passing arguments to the `AudiobookCurator`:

```python
# Skip the OpenAI rewrite step (faster and cheaper)
curator = AudiobookCurator(skip_llm=True)

# Point at a specific directory (avoids re-processing other files)
curator.curate_from_directory("input/audiobooks/networking")

# Override TTS provider
curator = AudiobookCurator(provider_override="smallest")

# Enable multi-speaker diarization
curator = AudiobookCurator(diarize=True)

# Combine overrides and change threshold
curator = AudiobookCurator(
    skip_llm=True, 
    provider_override="smallest", 
    chapterize_threshold=3000
)
```

> **Tip:** Use `--input-dir` to target a specific subfolder when you only want to process new files. This prevents the pipeline from re-scanning (and potentially re-trying) unrelated files.

### Re-run safety

The pipeline is **idempotent**. Episodes already in `completed` status are skipped automatically — no duplicate audio is generated. Episodes in `pending` or `failed` status will be re-attempted.

---

## Output

After a successful run you will see a summary like:

```
============================================================
  Results
============================================================
  Episodes generated : 9
  Playlists touched  : 1
  Errors             : 0

  ✅ Pipeline completed successfully!
```

**Where the files go:**

| Location | What |
|---|---|
| `outputs/audiobooks/<episode-id>/` | Per-episode MP3 and per-chapter MP3s |
| `.cache/audiobooks/` | TTS chunk cache (keyed by provider + voice + text hash) — avoids re-synthesizing unchanged chunks |
| Database `audio_episodes` | `audio_url`, `duration_seconds`, `chapters` JSON, `status = "completed"` |
| Supabase Storage | Public URL (if `SUPABASE_URL` + `SUPABASE_KEY` are set) |

---

## Legacy: Single-File Generation (No DB)

For quick one-off generation without touching the database, write a simple script:

```python
from app.services.audiobook.pipeline import AudiobookService

service = AudiobookService()
with open("input/audiobooks/some-article.txt") as f:
    text = f.read()

# Outputs to outputs/audiobooks/some-article.mp3
result = service.generate_from_text(text, skip_llm=True, title="some-article")
print("Saved to:", result["audio_url"])
```

This uses the `AudiobookService` wrapper which calls the audio pipeline directly and prints the output path. No playlist or episode records are created.

---

## Programmatic Usage

### Curate a directory

```python
from app.services.audiobook.curator import AudiobookCurator

curator = AudiobookCurator(skip_llm=True, diarize=True)
result = curator.curate_from_directory("input/audiobooks/networking")
# {'episodes_generated': 9, 'playlists_touched': 1, 'errors': [], 'success': True}
```

### Curate a single text string

```python
curator = AudiobookCurator(skip_llm=True)
result = curator.curate_single_text(
    text="Bitcoin is a decentralized...",
    title="Bitcoin Intro",
    playlist_slug="bitcoin-basics",
    playlist_title="Bitcoin Basics",
    source_url="https://example.com",
    tags=["bitcoin"],
)
print(result["episode"]["audio_url"])
```

### Raw audio generation (no DB writes)

```python
from app.services.audiobook.pipeline import AudioPipeline

pipeline = AudioPipeline()
episode = pipeline.generate_episode(
    text="Your text here...",
    title="My Episode",
    skip_llm=True,
    diarize=True,
)
print(f"Saved: {episode.audio_path}")
print(f"Duration: {episode.duration_seconds}s")
print(f"Chapters: {episode.chapters}")
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `mapping values are not allowed` YAML error | Wrap the field value containing `:` in double quotes |
| `ffmpeg not found` | Install ffmpeg and ensure it's on your `PATH` |
| `Database not configured` | Set `DATABASE_URL` in your `.env` |
| TTS 401 / 403 errors | Check your `DEEPGRAM_API_KEY` or `SMALLEST_API_KEY` |
| Episode stuck in `generating` | A previous run crashed mid-way. The next run will re-attempt it automatically |
| `context canceled` in terminal | The run was interrupted. Re-run — completed episodes will be skipped |
