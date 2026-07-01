# Audiobook Curation Pipeline

Transforms plain text files into organized audio playlists stored in the database. Supports two input types: standalone articles and multi-page series (like "Learn Me a Bitcoin").

## 🏗️ Architecture

```
app/services/audiobook/
├── __init__.py           # Package exports
├── config.py             # Loads audiobook_config.yaml + lexicon
├── ingestion.py          # Parses input files with YAML frontmatter
├── curator.py            # Orchestrator: ingest → generate → persist
├── playlist_service.py   # DB CRUD for playlists + episodes
├── pipeline.py           # Core audio engine (text → MP3)
├── rewrite.py            # LLM chapterization via OpenAI
├── textproc.py           # Text cleaning, normalization, chunking
├── tts.py                # TTS providers (Deepgram, Smallest AI)
├── stitch.py             # Audio stitching + loudness normalization
└── README.md             # This file
```

### Module Responsibilities

| Module | Responsibility |
|---|---|
| **`ingestion.py`** | Scans `input/audiobooks/`, parses YAML frontmatter, returns structured `InputFile` objects. Groups series files by `series_slug`. |
| **`curator.py`** | The orchestrator. Reads ingested files → decides single vs. series strategy → calls pipeline for TTS → calls playlist_service for DB writes. |
| **`playlist_service.py`** | Pure database CRUD. `find_or_create_playlist()`, `create_episode()`, `refresh_playlist_stats()`, etc. |
| **`pipeline.py`** | Stateless audio engine. Converts text → cleaned text → (optional LLM rewrite) → TTS chunks → stitched MP3. Returns a `GeneratedEpisode` dataclass. |
| **`rewrite.py`** | Sends text to OpenAI to produce a chapterized narration script. |
| **`textproc.py`** | Regex-based text cleaning (strips timestamps, speaker tags), lexicon substitution, sentence-boundary chunking. |
| **`tts.py`** | Abstract `TTSProvider` with implementations for Deepgram and Smallest AI. |
| **`stitch.py`** | Uses `pydub` to concatenate audio chunks, insert silence gaps, and normalize loudness. |

## 🚀 How to Run (Step-by-Step)

**Step 1: Install Dependencies**
```bash
pip install -r requirements.txt
```

**Step 2: Set Environment Variables**
Ensure your `.env` file in the project root has these keys:
```env
OPENAI_API_KEY=your_openai_key
DEEPGRAM_API_KEY=your_deepgram_key
SMALLEST_API_KEY=your_smallest_key
```

**Step 3: Run Database Migration**
The pipeline uses `audio_playlists` and `audio_episodes` tables:
```bash
python scripts/migrate_schema.py
```

**Step 4: Prepare Input Files**
Place `.txt` files in `input/audiobooks/`. Each file needs YAML frontmatter at the top (see Input Format below).

**Step 5: Run the Curation Pipeline**
```bash
# Full pipeline (with LLM rewrite for long articles)
python curate_audiobooks.py

# Skip LLM rewrite (faster, cheaper — straight to TTS)
python curate_audiobooks.py --skip-llm

# Use a specific TTS provider
python curate_audiobooks.py --provider smallest

# Custom input directory
python curate_audiobooks.py --input-dir path/to/files
```

## 📄 Input File Format

### Single Article (newsletter, blog post)
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

### Series (multi-page guide)
Each page is a separate `.txt` file. Files are grouped by `series_slug` and ordered by `sequence_number`.
```text
---
type: series
series_slug: learn-me-a-bitcoin
series_title: Learn Me a Bitcoin
sequence_number: 1
title: What is Bitcoin?
author: Greg Walker
source_url: https://learnmeabitcoin.com/what-is-bitcoin
tags: ["bitcoin", "basics"]
---
Bitcoin is a computer program that allows people to...
```

### Plain Text (no frontmatter)
Files without YAML frontmatter are automatically treated as single articles. The filename becomes the title.

## 🧩 How to Use in Code

### Full Curation Pipeline
```python
from app.services.audiobook.curator import AudiobookCurator

curator = AudiobookCurator(skip_llm=True)
result = curator.curate_from_directory("input/audiobooks")
print(result)
# {'episodes_generated': 4, 'playlists_touched': 2, ...}
```

### Generate a Single Episode Programmatically
```python
from app.services.audiobook.curator import AudiobookCurator

curator = AudiobookCurator(skip_llm=True)
result = curator.curate_single_text(
    text="Bitcoin is a decentralized digital currency...",
    title="Bitcoin Intro",
    playlist_slug="bitcoin-basics",
    playlist_title="Bitcoin Basics",
)
print(result["episode"]["audio_url"])
```

### Low-Level Audio Generation (No DB)
```python
from app.services.audiobook.pipeline import AudioPipeline

pipeline = AudioPipeline()
episode = pipeline.generate_episode(
    text="Your text here...",
    title="My Episode",
    skip_llm=True,
)
print(f"Saved to: {episode.audio_path}")
print(f"Duration: {episode.duration_seconds}s")
```

## ⚙️ Configuration

- **`app/services/audiobook_config.yaml`** — TTS provider settings, LLM model, audio formatting
- **`app/services/audiobook_lexicon.json`** — Domain-specific pronunciation overrides (e.g., "DeFi" → "dee-fye")

## 🔑 Environment Variables

Loaded automatically from the project root `.env`:
```env
OPENAI_API_KEY=      # LLM rewrite (only needed if NOT using --skip-llm)
DEEPGRAM_API_KEY=    # Deepgram TTS provider
SMALLEST_API_KEY=    # Smallest AI TTS provider
```

## 🛠️ System Requirements

`ffmpeg` must be installed on the system PATH (required by `pydub`):
- **Ubuntu/Debian**: `sudo apt install ffmpeg`
- **Mac**: `brew install ffmpeg`
- **Windows**: `winget install Gyan.FFmpeg`
