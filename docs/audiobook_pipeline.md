# Audiobook Curation Pipeline — Complete Documentation

> **What this system does:** Takes plain text files (articles, guides, transcripts) and converts them into narrated audio episodes organized into topic-specific playlists, stored in a database and optionally uploaded to cloud storage.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Input Format](#2-input-format)
3. [Step-by-Step Pipeline](#3-step-by-step-pipeline)
4. [Output: Topic-Specific Playlists](#4-output-topic-specific-playlists)
5. [Configuration Reference](#5-configuration-reference)
6. [Major Challenges & How They Are Solved](#6-major-challenges--how-they-are-solved)
7. [Module Map](#7-module-map)

---

## 1. System Overview

```
INPUT                    PROCESSING                         OUTPUT
──────────────────────   ─────────────────────────────────  ──────────────────────────────
.txt files               ┌───────────────────────────────┐  audio_playlists (DB)
  ├── single articles    │  1. Ingestion                  │    ├── "Learn Me a Bitcoin" (series)
  └── series parts       │  2. Curator routing            │    │     ├── ep1.mp3
                         │  3. Text cleaning              │    │     ├── ep2.mp3
                     ──► │  4. LLM chapterization         │──► │     └── ep3.mp3
                         │  5. Normalization / chunking   │    │
                         │  6. TTS synthesis              │    └── "Bitcoin Mining Economics" (collection)
                         │  7. Audio stitching            │          └── episode.mp3
                         │  8. Supabase upload            │
                         │  9. DB persistence             │  Supabase Storage (optional CDN)
                         └───────────────────────────────┘
```

The system has two **entry points**:

| Entry Point | Purpose |
|---|---|
| `python curate_audiobooks.py` | CLI — batch-processes a directory of `.txt` files |
| `AudiobookCurator.curate_single_text(text, title, ...)` | Programmatic API — process one article from code |

---

## 2. Input Format

All input files are plain `.txt` files placed in `input/audiobooks/` (or any directory). Three forms are supported:

### 2a. Single Article (with YAML frontmatter)

Used for standalone content: newsletters, blog posts, essays.

```text
---
type: single_article
title: "Bitcoin Mining Economics in 2025"
author: "Lyn Alden"
source_url: "https://example.com/article"
tags: ["mining", "economics"]
description: "A deep dive into mining profitability."
---

The actual article text goes here. It can be thousands of words long.
The pipeline will clean it, optionally rewrite it into chapters via an LLM,
then convert the whole thing to audio.
```

### 2b. Series Part (multi-page guide)

Each page of a multi-part guide is its own `.txt` file. Files are linked together via `series_slug` and ordered by `sequence_number`. All files in the same series produce a **single playlist** in the database.

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

Mining is the process by which new Bitcoin transactions are confirmed...
```

### 2c. Plain Text (no frontmatter)

Files with no `---` block are auto-treated as single articles. The filename (minus extension, underscores/dashes replaced with spaces, title-cased) becomes the episode title.

```text
Bitcoin is a decentralized peer-to-peer electronic cash system...
```

### Frontmatter Field Reference

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | No (defaults to `single_article`) | `single_article` or `series` | Determines routing strategy |
| `title` | No (falls back to filename) | string | Episode title |
| `author` | No | string | Attribution metadata |
| `source_url` | No | string | Source link stored in DB |
| `tags` | No | list of strings | Topic tags; become playlist tags |
| `description` | No | string | Stored in DB, not narrated |
| `series_slug` | **Required for series** | string (URL-safe) | Groups files into one playlist |
| `series_title` | **Required for series** | string | Playlist display title |
| `sequence_number` | **Required for series** | integer | Ordering within the playlist |

---

## 3. Step-by-Step Pipeline

```
.txt file on disk
      |
      v
 [STEP 1]  INGESTION  (ingestion.py)
   parse_file()    -> InputFile dataclass
   group_series()  -> dict[slug -> [InputFile, ...]]
      |
      |  singles                  |  series groups
      v                           v
 [STEP 2]  CURATOR ROUTING  (curator.py)
   _process_single_article()   OR   _process_series()
   find_or_create_playlist() + find_or_create_episode()
      |
      |  per episode
      v
 [STEP 3]  TEXT CLEANING  (textproc.py -> clean_text)
   Strip timestamps, speaker labels, stage directions, extra whitespace
      |
      v
 [STEP 4]  LLM REWRITE  (rewrite.py)  [skipped for series or short articles]
   OpenAI GPT-4.1  ->  JSON manifest: title + chapters[]
      |
      |  chapters[] of text
      v  (per chapter, per speaker chunk)
 [STEP 5]  NORMALIZE + CHUNK  (textproc.py -> normalize + chunk_split)
   Expand $1.5M -> "one point five million dollars"
   Expand acronyms, years, ordinals via num2words
   Split into TTS-safe character-limited pieces
      |
      v
 [STEP 6]  TTS SYNTHESIS  (tts.py + disk cache)
   Per chunk: check SHA-256 disk cache -> call Deepgram / Smallest AI API
   Diarization: assign distinct voice per speaker
      |
      v
 [STEP 7]  STITCH  (stitch.py)
   build_chapter(): concat chunks + 220 ms silence gaps
   export_book():   concat chapters + 700 ms silence gaps + loudness normalize -20 dBFS
   -> outputs/audiobooks/<episode-id>/<Title>.mp3
      |
      v
 [STEP 8]  SUPABASE UPLOAD  (storage.py)  [optional]
   POST audiobooks/<Playlist>/<Episode>.mp3  ->  returns public CDN URL
      |
      v
 [STEP 9]  DB PERSISTENCE  (playlist_service.py)
   update_episode(audio_url, duration_seconds, chapters, status="completed")
   refresh_playlist_stats(episode_count, total_duration_seconds)
```

---

### Step 1 — Ingestion (`ingestion.py`)

**File:** `app/services/audiobook/ingestion.py`

1. `scan_input_directory(path)` globs all `*.txt` files and calls `parse_file()` on each.
2. `parse_file()` reads the raw file and applies the regex `^---\n...\n---\n` to detect YAML frontmatter:
   - **No frontmatter found** → treated as `single_article`; filename stem is title-cased as the title.
   - **Frontmatter found** → `yaml.safe_load()` parses the metadata block; required fields are validated.
   - **Empty body** → logged and skipped.
3. Returns an `InputFile` dataclass for each successfully parsed file.
4. `group_series(inputs)` groups series files by `series_slug`, sorted by `sequence_number`.

**`InputFile` dataclass:**

```python
@dataclass
class InputFile:
    filepath: Path
    input_type: str          # 'single_article' or 'series'
    title: str
    body: str
    series_slug: Optional[str]
    series_title: Optional[str]
    sequence_number: int
    author: Optional[str]
    source_url: Optional[str]
    description: Optional[str]
    tags: list[str]
    word_count: int          # computed: len(body.split())
```

---

### Step 2 — Curation Routing (`curator.py`)

**File:** `app/services/audiobook/curator.py`

`AudiobookCurator` is the orchestrator. After ingestion it routes work based on input type:

**Series groups → `_process_series(slug, files)`**

1. Calls `find_or_create_playlist(slug, series_title, playlist_type="series", tags=...)`.
2. Iterates files in sequence order; calls `find_or_create_episode()` for each.
3. Calls `_generate_and_update(episode, body, skip_llm=True)` — series episodes are already logically divided, so the LLM step is always bypassed.

**Single articles → `_process_single_article(inp)`**

1. Derives a URL-safe `slug` from the article title via `_slugify()`.
2. Calls `find_or_create_playlist(slug, title, playlist_type="collection")`.
3. Creates a single episode in the playlist.
4. Calls `_generate_and_update(episode, body, skip_llm)` where `skip_llm=True` only if word count ≤ `chapterize_threshold` (default: **5,000 words**).

**`_generate_and_update()` — bridge between curator and pipeline:**

```
episode.status == "completed"  -->  skip entirely (idempotency guard)
episode.status == "pending"    -->  set "generating" -> run pipeline -> set "completed"
episode.status == "failed"     -->  re-attempt automatically
```

On success: writes `audio_url`, `duration_seconds`, `chapters`, `status = "completed"` to the DB.
On failure: sets `status = "failed"` and re-raises the exception.

---

### Step 3 — Text Cleaning (`textproc.py → clean_text`)

**File:** `app/services/audiobook/textproc.py`

Strips content that sounds bad or meaningless when read aloud:

| What is removed | Examples |
|---|---|
| Timestamps | `[00:12:45]`, `(1:30)` |
| Speaker labels | `ALICE: `, `Host: ` |
| Stage directions | `[laughter]`, `(applause)` |
| Excess whitespace / blank lines | Collapsed to single spaces / single blank lines |

> **Diarization exception:** When `diarize=True`, speaker labels are **retained** — they are used in Step 5 to assign different TTS voices to each speaker.

---

### Step 4 — LLM Rewrite & Chapterization (`rewrite.py`)

**File:** `app/services/audiobook/rewrite.py`

**Skipped when:** `skip_llm=True`, `diarize=True`, or article word count ≤ `chapterize_threshold`.

**When active:**

1. If text exceeds `max_words_per_request` (default 3,000 words), it is split into chunks and sent in multiple API calls; results are merged into one manifest.
2. Sends to **OpenAI GPT-4.1** (temperature 0.3) with a system prompt that instructs the model to act as an audiobook editor — removing filler words, smoothing sentences, and splitting into logical chapters.
3. Returns a structured JSON manifest:

```json
{
  "title": "Episode Title",
  "chapters": [
    {"title": "Chapter 1: Introduction", "text": "Narration text..."},
    {"title": "Chapter 2: Deep Dive",    "text": "More narration..."}
  ]
}
```

4. The caller's title always **overrides** the LLM-generated title to preserve DB consistency.
5. **Fallback:** If the LLM returns zero chapters (bad JSON, network error, empty response), a single-chapter manifest is built directly from the cleaned text.

---

### Step 5 — Text Normalization & Chunking (`textproc.py → normalize + chunk_split`)

**File:** `app/services/audiobook/textproc.py`

Runs **per chapter, per speaker chunk**.

#### Diarization (if enabled)

`parse_diarization(text)` splits the chapter text into speaker-attributed segments:

```python
[
  {"speaker": "Host",  "text": "Welcome to the show..."},
  {"speaker": "Guest", "text": "Thanks for having me..."},
]
```

Each unique speaker is assigned a distinct TTS voice in Step 6.

#### Normalization (`normalize`)

Converts written forms to speech-natural forms:

| Input | Output | Method |
|---|---|---|
| `$1.5M` | `1.5 million dollars` | Regex + scale map |
| `2009` | `two thousand nine` | `num2words` |
| `21st` | `twenty-first` | `num2words` |
| `42,000` | `forty-two thousand` | `num2words` |
| `AWS` | `A-W-S` | Auto-hyphenation |
| `NASA` | `NASA` | Pronounceable exceptions list |
| `BTC` | `bitcoin` | `audiobook_lexicon.json` |

The **lexicon** (`audiobook_lexicon.json`) holds domain-specific substitutions applied before the general acronym pass:

```json
{
  "BTC":    "bitcoin",
  "UTXO":   "U-T-X-O",
  "DeFi":   "dee-fye",
  "PoW":    "proof of work",
  "ASIC":   "ay-sick",
  "mempool":"mem pool"
}
```

#### Chunking (`chunk_split`)

TTS APIs have per-request character limits. Chunks are produced using a multi-tier strategy:

1. Split at **sentence boundaries** via NLTK `sent_tokenize` (regex fallback if NLTK unavailable).
2. If a sentence still exceeds the limit → split at **prosody boundaries**: `;` `:` `,` `—` `-`.
3. If a single word exceeds the limit (e.g. a long URL) → split at the **character level**.

Character limits (from `audiobook_config.yaml`):

| Provider | Max chars / request |
|---|---|
| Deepgram | 1,900 |
| Smallest AI | 240 |

---

### Step 6 — TTS Synthesis (`tts.py`)

**File:** `app/services/audiobook/tts.py`

#### Provider Architecture

Abstract `TTSProvider` base class with two concrete implementations:

| Provider | Class | API Endpoint |
|---|---|---|
| Deepgram | `DeepgramTTS` | `https://api.deepgram.com/v1/speak` |
| Smallest AI | `SmallestTTS` | `https://api.smallest.ai/waves/v1/tts` |

Selected via `tts.provider` in `audiobook_config.yaml`. Overridable at runtime with `--provider`.

#### Voice Selection (Diarization)

When `diarize=True`, each unique speaker maps to a distinct voice from a provider-specific pool. The mapping is **consistent across chapters** — the same speaker always gets the same voice:

- **Deepgram pool:** `aura-asteria-en`, `aura-orion-en`, `aura-arcas-en`, `aura-perseus-en`, `aura-helios-en`, `aura-angus-en`
- **Smallest AI pool:** `emily`, `james`, `lucy`, `michael`, `sarah`

#### TTS Chunk Cache

Every synthesis call is memoized to disk:

```
Cache key  = SHA-256(provider | voice | format | text | lex_hash | speed | model)[:24 hex chars]
Cache path = .cache/audiobooks/<cache_key>.mp3
```

- **Cache hit** → reads bytes from disk. Zero API calls, near-instant.
- **Cache miss** → calls TTS API, writes bytes to disk.
- **Lexicon invalidation** → the lexicon JSON content is hashed into the key, so updating `audiobook_lexicon.json` automatically invalidates stale cached audio.

---

### Step 7 — Audio Stitching (`stitch.py`)

**File:** `app/services/audiobook/stitch.py`

Uses `pydub` (backed by `ffmpeg`) to assemble raw audio bytes into a polished final file.

**`build_chapter(chunks, cfg)`**

1. Decodes each raw-bytes chunk into a `pydub.AudioSegment`.
2. Normalizes all chunks to the same sample rate, channels, and sample width (taken from the first chunk).
3. Concatenates with **220 ms silence gaps** between chunks (configurable).

**`export_book(chapters, cfg, out_path)`**

1. Concatenates chapter segments with **700 ms silence gaps** — simulating a chapter break.
2. Runs `normalize_loudness()` → targets **−20 dBFS** across the entire file.
3. Exports final `.mp3` to disk.

**Output file structure:**

```
outputs/audiobooks/<episode-uuid>/
  ├── ch01.mp3              <- chapter 1 audio
  ├── ch02.mp3              <- chapter 2 audio
  └── Episode Title.mp3     <- final stitched audiobook
```

---

### Step 8 — Cloud Storage Upload (`storage.py`)

**File:** `app/services/audiobook/storage.py`

Optional — only runs if `SUPABASE_URL` and `SUPABASE_KEY` are set in the environment.

- Uploads the final `.mp3` to Supabase Storage bucket `audiobooks`.
- Destination path: `<Safe Playlist Title>/<Safe Episode Title>.mp3` (special characters stripped to prevent path traversal).
- Uses `x-upsert: true` header — safe to re-upload without conflicts.
- Returns the public CDN URL on success; returns `None` (falls back to local absolute path) on failure.

---

### Step 9 — Database Persistence (`playlist_service.py`)

**File:** `app/services/audiobook/playlist_service.py`

All DB operations go through `PlaylistService`, a pure data-access layer using SQLAlchemy sessions.

#### `audio_playlists` table schema

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Auto-generated |
| `title` | Text | Display title |
| `slug` | Text (unique) | URL-safe identifier |
| `playlist_type` | Text | `series` or `collection` |
| `tags` | JSONB | Topic tag list |
| `status` | Text | `draft` / `published` / `archived` |
| `episode_count` | Integer | Cached count of completed episodes |
| `total_duration_seconds` | Integer | Cached sum of episode durations |
| `cover_image_url` | Text | Optional cover art URL |

#### `audio_episodes` table schema

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Auto-generated |
| `playlist_id` | UUID FK | Parent playlist (CASCADE delete) |
| `title` | Text | Episode title |
| `sequence_number` | Integer | Ordering (unique per playlist) |
| `audio_url` | Text | Local path or Supabase CDN URL |
| `duration_seconds` | Integer | Computed from final audio file |
| `source_url` | Text | Original article URL |
| `status` | Text | `pending` / `generating` / `completed` / `failed` |
| `chapters` | JSONB | Array of `{title, text}` dicts |
| `metadata` | JSONB | `{author, word_count, source_file}` |

#### Key `PlaylistService` operations

| Method | Behaviour |
|---|---|
| `find_or_create_playlist(slug, ...)` | Upsert by slug — returns existing or creates new in `draft` status |
| `find_or_create_episode(playlist_id, seq_num, ...)` | Upsert by `(playlist_id, sequence_number)` — returns existing or creates new in `pending` status |
| `update_episode(id, updates)` | Sets `status`, `audio_url`, `duration_seconds`, `chapters` |
| `refresh_playlist_stats(playlist_id)` | Recomputes `episode_count` + `total_duration_seconds` from all `completed` episodes |

---

## 4. Output: Topic-Specific Playlists

### `series` Playlist

One playlist per `series_slug`. Multiple `.txt` files sharing the same `series_slug` merge into one ordered playlist.

```
Playlist: "Learn Me a Bitcoin"
  type: series  |  slug: learn-me-a-bitcoin  |  tags: ["bitcoin"]

  Episode 1: "What is Bitcoin?"          seq=1  duration=420s  status=completed
  Episode 2: "Transactions Explained"    seq=2  duration=380s  status=completed
  Episode 3: "Mining and Proof of Work"  seq=3  duration=510s  status=completed
  ...
```

### `collection` Playlist

One playlist per standalone article. Contains exactly one episode.

```
Playlist: "Bitcoin Mining Economics in 2025"
  type: collection  |  slug: bitcoin-mining-economics-in-2025

  Episode 1: "Bitcoin Mining Economics in 2025"  seq=1  duration=890s  status=completed
```

### REST API — Read Playlists

After the pipeline runs, playlists and episodes are queryable via the FastAPI server:

| Endpoint | Description |
|---|---|
| `GET /audiobooks/playlists` | List all playlists (filter by `status`, `playlist_type`; paginate with `limit`/`offset`) |
| `GET /audiobooks/playlists/{slug}` | Single playlist with all ordered episodes |
| `GET /audiobooks/episodes/{episode_id}` | Single episode by UUID |

---

## 5. Configuration Reference

**`app/services/audiobook_config.yaml`**

```yaml
llm:
  provider: openai
  model: gpt-4.1              # rewrite/chapterize model
  temperature: 0.3
  max_words_per_request: 3000 # splits long articles before sending to LLM

tts:
  provider: deepgram           # deepgram | smallest
  voices:
    deepgram: aura-2-thalia-en
    smallest: meher             # also: magnus, olivia, aarush
  models:
    smallest: lightning_v3.1_pro
  max_chars:
    deepgram: 1900              # per-request character cap
    smallest: 240
  speed: 1.0
  format: mp3

audio:
  silence_ms_between_chunks: 220     # gap between TTS chunks within a chapter
  silence_ms_between_chapters: 700   # gap between chapters in the final file
  target_dbfs: -20.0                 # loudness normalization target

paths:
  output_dir: outputs/audiobooks
  cache_dir: .cache/audiobooks
  lexicon: audiobook_lexicon.json
```

**Environment Variables (`.env` file)**

| Variable | Purpose | Required |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Always |
| `OPENAI_API_KEY` | GPT-4.1 for LLM rewrite | Only if not using `--skip-llm` |
| `DEEPGRAM_API_KEY` | Deepgram TTS provider | If using Deepgram |
| `SMALLEST_API_KEY` | Smallest AI TTS provider | If using Smallest AI |
| `SUPABASE_URL` | Supabase project URL | Optional (CDN upload) |
| `SUPABASE_KEY` | Supabase service-role key | Optional (CDN upload) |

---

## 6. Major Challenges & How They Are Solved

### Challenge 1 — TTS APIs Have Strict Per-Request Character Limits

**Problem:** Deepgram caps each request at 1,900 characters; Smallest AI at 240 characters. A single article can be 50,000+ characters. Splitting naively at the limit mid-sentence produces broken, unnatural audio.

**Solution:** `chunk_split()` in `textproc.py` uses a **multi-tier splitting strategy**:

1. Split at **sentence boundaries** via NLTK `sent_tokenize` (regex fallback if unavailable).
2. If a sentence still exceeds the limit → split at **prosody boundaries**: `;` `:` `,` `—` `-`.
3. If a single word exceeds the limit (e.g. a very long URL) → split at the **character level** as a last resort.

This guarantees all chunks fit within API limits while preserving natural speech rhythm.

---

### Challenge 2 — Domain-Specific Acronyms Sound Wrong in TTS

**Problem:** Technical content is full of acronyms (`BTC`, `UTXO`, `PoW`, `DeFi`) that TTS systems mispronounce or garble. For example, `UTXO` may be read as a single nonsense word.

**Solution:** A two-layer pronunciation system:

1. **Lexicon substitution** (`audiobook_lexicon.json`): domain-specific term → spoken form. Applied via whole-word regex substitution before TTS synthesis. Example: `UTXO` → `U-T-X-O`, `DeFi` → `dee-fye`.
2. **Automatic acronym expansion** in `normalize()`: any uppercase acronym not in the pronounceable exceptions list (`NASA`, `NATO`, etc.) or the lexicon is automatically hyphenated — `AWS` → `A-W-S`.

The lexicon content is hashed into the TTS cache key, so updating `audiobook_lexicon.json` automatically invalidates stale cached audio.

---

### Challenge 3 — Re-running the Pipeline Wastes API Credits

**Problem:** TTS and LLM calls are expensive. If the pipeline crashes or is re-run after adding new files, it would naively re-synthesize all previously generated audio.

**Solution:** Two independent caching layers:

1. **Episode-level DB idempotency:** Episodes already in `completed` status are skipped immediately in `_generate_and_update()`. No TTS or LLM calls happen.
2. **Chunk-level disk cache:** Each text chunk is keyed by a SHA-256 hash of `provider + voice + format + text + lex_hash + speed + model`. The first 24 hex chars form the filename in `.cache/audiobooks/`. Cache hits cost zero API calls and are near-instant.

Re-running after a crash only processes truly new or `failed` episodes.

---

### Challenge 4 — Long Articles Need Chapter Structure; Short Articles Do Not

**Problem:** A 10,000-word article converted to audio as one block is monotonous. A 200-word article sent to GPT-4.1 for chapterization is wasteful.

**Solution:** Adaptive LLM gating via `chapterize_threshold` (default: **5,000 words**):

| Input | LLM Used? | Reason |
|---|---|---|
| Article < 5,000 words | No | Single-chapter manifest built from cleaned text |
| Article >= 5,000 words | Yes | GPT-4.1 structures text into titled chapters |
| Series episode (any length) | Never | Series structure already provides logical division |

The threshold is configurable at CLI runtime: `python curate_audiobooks.py --threshold 3000`.

---

### Challenge 5 — Multi-Speaker Content Gets a Single Robotic Voice

**Problem:** Podcast transcripts, interviews, and Q&A content have multiple speakers. A single TTS voice makes it impossible to follow the conversation.

**Solution:** Optional **diarization mode** (`--diarize` flag or `diarize=True`):

1. `clean_text()` is called with `retain_speakers=True` — speaker labels like `Host:` and `Guest:` are preserved instead of stripped.
2. `parse_diarization()` splits each chapter into `{speaker, text}` segments.
3. The pipeline maintains a `speaker_voice_map` dictionary. Each new speaker name gets the next voice from the provider-specific pool.
4. The voice map is **consistent across chapters** — the same speaker always gets the same voice throughout the entire episode.

---

### Challenge 6 — Numbers, Dates, and Special Symbols Sound Wrong

**Problem:** Text like `$1.5M`, `21st`, `2009`, or `AWS` will be read literally or garbled. `$1.5M` might become "dollar one point five M".

**Solution:** The `normalize()` function uses `num2words` + regex to expand written forms before TTS synthesis:

| Pattern | Before | After |
|---|---|---|
| Currency | `$1.5M` | `1.5 million dollars` |
| Years | `2009` | `two thousand nine` |
| Ordinals | `21st` | `twenty-first` |
| Plain numbers | `42,000` | `forty-two thousand` |
| Unpronounceable acronyms | `AWS` | `A-W-S` |
| Pronounceable acronyms | `NASA` | `NASA` (unchanged) |
| Domain terms | `BTC` | `bitcoin` (via lexicon) |

`num2words` is optional — if not installed, numeric expansions are gracefully skipped and the original text is passed through unchanged.

---

### Challenge 7 — Audio Segments Have Inconsistent Volume Levels

**Problem:** Different TTS providers and even different API calls within the same provider return audio at varying loudness. Concatenating them produces jarring volume jumps in the final audiobook.

**Solution:** After all chapters are stitched together, `export_book()` in `stitch.py` runs loudness normalization:

```python
def normalize_loudness(seg: AudioSegment, target_dbfs: float) -> AudioSegment:
    gain = target_dbfs - seg.dBFS
    return seg.apply_gain(min(gain, -seg.max_dBFS))
```

Applied to the **full stitched file** (not individual chunks), so relative dynamics within chapters are preserved while overall loudness is standardized to **−20 dBFS** (configurable).

---

### Challenge 8 — Concurrent Runs Can Cause Database Race Conditions

**Problem:** Running the pipeline concurrently, or re-running after an interrupted run, could attempt to create the same playlist or episode record twice — causing `IntegrityError` exceptions.

**Solution:** `find_or_create_playlist()` and `find_or_create_episode()` use an **optimistic concurrency pattern**:

```python
# 1. Try to fetch existing record
pl = session.query(AudioPlaylist).filter_by(slug=slug).first()
if pl:
    return pl.to_dict()

# 2. Try to insert new record
session.add(new_pl)
try:
    session.commit()
except IntegrityError:
    # 3. Race condition: another process inserted first — fetch and return theirs
    session.rollback()
    pl = session.query(AudioPlaylist).filter_by(slug=slug).first()
    return pl.to_dict()
```

This pattern avoids application-level locks and is safe with PostgreSQL's unique constraint enforcement.

---

## 7. Module Map

```
app/services/audiobook/
├── config.py            Loads audiobook_config.yaml + audiobook_lexicon.json; injects API keys from .env
├── ingestion.py         Parses .txt files with YAML frontmatter -> InputFile dataclasses
├── curator.py           Orchestrator: routes singles vs. series -> pipeline -> DB
├── pipeline.py          Core audio engine: text -> GeneratedEpisode (stateless, no DB writes)
├── rewrite.py           OpenAI GPT-4.1 chapterization -> {title, chapters[]} JSON
├── textproc.py          clean_text, normalize, chunk_split, parse_diarization
├── tts.py               TTSProvider (abstract) + DeepgramTTS + SmallestTTS
├── stitch.py            pydub-based concatenation + silence gaps + loudness normalize
├── storage.py           Supabase Storage REST upload -> public URL
└── playlist_service.py  SQLAlchemy CRUD for audio_playlists + audio_episodes tables

app/models.py            AudioPlaylist + AudioEpisode ORM models (DB schema)
routes/audiobooks.py     FastAPI read-only REST API (GET /audiobooks/playlists, /episodes)
curate_audiobooks.py     CLI entry point (argparse wrapper around AudiobookCurator)
generate_audiobook.py    Legacy single-file CLI (no DB, uses AudiobookService wrapper)
```
