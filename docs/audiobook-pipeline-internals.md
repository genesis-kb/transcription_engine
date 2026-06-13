# Audiobook Pipeline — Architecture & Step-by-Step Internals

This document explains what happens inside the pipeline from the moment you run `python curate_audiobooks.py` to the moment a playable audio URL lands in the database.

---

## High-Level Data Flow

```
.txt files (input/)
        │
        ▼
  [1] INGESTION           ingestion.py
  Parse YAML frontmatter
  Return InputFile objects
        │
        ├─── series files ──────────────────────┐
        │                                       │
        └─── single articles ─────┐             │
                                  ▼             ▼
                          [2] CURATOR          curator.py
                          Route: single vs. series
                          Call pipeline per episode
                          Call playlist_service for DB writes
                                  │
                                  ▼
                          [3] PIPELINE         pipeline.py
                          clean → rewrite → TTS → stitch
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              [3a] textproc  [3b] rewrite   [3c] tts
              clean_text()   OpenAI LLM    Deepgram /
              normalize()    chapterize    Smallest AI
              chunk_split()
                                  │
                                  ▼
                          [3d] STITCH          stitch.py
                          pydub concatenation
                          silence gaps + loudness normalize
                                  │
                                  ▼
                          [4] STORAGE          storage.py
                          Upload MP3 → Supabase (optional)
                          Returns public URL
                                  │
                                  ▼
                          [5] DATABASE         playlist_service.py
                          Update audio_episodes:
                          audio_url, duration, chapters, status
```

---

## Module Responsibilities

| Module | File | What it does |
|---|---|---|
| **Ingestion** | `ingestion.py` | Scans input directory, parses YAML frontmatter, returns `InputFile` dataclass objects. Groups series files by `series_slug`. |
| **Curator** | `curator.py` | The orchestrator. Routes singles vs. series. Calls the pipeline for each episode and writes results to DB via `PlaylistService`. |
| **Pipeline** | `pipeline.py` | Stateless audio engine. Takes raw text in, produces a `GeneratedEpisode` (path + duration + chapters) out. Does **not** write to DB. |
| **Text Processing** | `textproc.py` | Advanced text cleaning (preserves speakers if `retain_speakers=True`), `num2words`-based number/date expansion, acronym handling, NLTK-based semantic chunking, and diarization parsing. |
| **Rewrite** | `rewrite.py` | Sends text to OpenAI GPT-4.1. Returns a chapterized narration script as JSON. |
| **TTS** | `tts.py` | Abstract `TTSProvider` with `DeepgramTTS` and `SmallestTTS` implementations. Injects pronunciation lexicons natively into the generation logic. |
| **Stitch** | `stitch.py` | Uses `pydub` to concatenate audio chunks, insert silence gaps between chunks and chapters, and normalize loudness. |
| **Storage** | `storage.py` | Uploads the final MP3 to Supabase Storage via REST API. Returns the public URL (or `None` if unconfigured). |
| **Playlist Service** | `playlist_service.py` | All DB CRUD. `find_or_create_playlist()`, `find_or_create_episode()`, `update_episode()`, `refresh_playlist_stats()`. |
| **Config** | `config.py` | Loads `audiobook_config.yaml` + `audiobook_lexicon.json`. Injects API keys from env. Returns `(cfg, lexicon)` tuple. |

---

## Step-by-Step Pipeline Internals

### Step 1 — Ingestion (`ingestion.py`)

`scan_input_directory(path)` globs all `*.txt` files and calls `parse_file()` on each.

`parse_file()` does the following:
1. Reads the raw file text.
2. Applies a regex (`^---\n...\n---\n`) to detect YAML frontmatter.
3. If no frontmatter is found → treated as `single_article`; filename becomes the title.
4. If frontmatter is found → `yaml.safe_load()` parses the metadata block.
5. Returns an `InputFile` dataclass with fields: `filepath`, `input_type`, `title`, `body`, `series_slug`, `sequence_number`, `author`, `source_url`, `description`, `tags`.

`group_series()` separates series files from singles and groups them by `series_slug`, sorted by `sequence_number`.

---

### Step 2 — Curator routes the work (`curator.py`)

`curate_from_directory()` calls ingestion, then:

- **Series group** → `_process_series(slug, files)`
  - Calls `find_or_create_playlist()` with `playlist_type="series"`.
  - Iterates over files in sequence order.
  - For each file: calls `find_or_create_episode()`, then `_generate_and_update()` with `skip_llm=True` (series episodes are already logically divided — no LLM chapterization needed).

- **Single article** → `_process_single_article(inp)`
  - Calls `find_or_create_playlist()` with `playlist_type="collection"`.
  - Creates one episode.
  - Calls `_generate_and_update()` with `skip_llm` determined by whether word count exceeds the threshold (default: 5,000 words).

`_generate_and_update()` is the bridge between curator and pipeline:
1. Checks episode status — skips if `completed`.
2. Sets status to `generating` in DB.
3. Calls `pipeline.generate_episode()`.
4. Optionally uploads to Supabase via `upload_to_supabase()`.
5. Updates the episode record with `audio_url`, `duration_seconds`, `chapters`, and `status = "completed"`.
6. On failure: sets `status = "failed"` and re-raises.

---

### Step 3 — Audio Pipeline (`pipeline.py`)

`AudioPipeline.generate_episode(text, title, skip_llm, ...)` runs these stages in order:

#### 3a — Text Cleaning (`textproc.clean_text`)

Strips content that doesn't read well aloud:
- Timestamps like `[00:12:45]` or `(1:30)`
- Speaker labels like `ALICE: ` or `Host: ` (unless `diarize=True` / `retain_speakers=True` is passed)
- Stage directions like `[laughter]`, `(applause)`
- Collapses excess whitespace and blank lines

#### 3b — LLM Rewrite / Chapterization (`rewrite.rewrite`)

Skipped if `skip_llm=True` (either via `--skip-llm` flag, or because the article is short enough).

When active:
1. Sends the cleaned text to OpenAI GPT-4.1 with a system prompt instructing it to act as an audiobook editor.
2. The model returns structured JSON:
   ```json
   {
     "title": "Episode Title",
     "chapters": [
       {"title": "Chapter 1 Title", "text": "Narration text..."},
       {"title": "Chapter 2 Title", "text": "Narration text..."}
     ]
   }
   ```
3. The caller's title always overrides the LLM-generated title (to preserve consistency with the DB record).

When skipped, a single-chapter manifest is built directly from the cleaned text.

#### 3c — Normalization, Diarization, + Chunking (`textproc.py`)

For each chapter:

1. **Diarization (`parse_diarization`)** — If `diarize=True`, parses speaker labels into chunks mapping speakers to their dialogue. Otherwise, treats the text as a single default chunk.
2. **`normalize(text)`** — Expands monetary values, uses `num2words` for robust year/date/ordinal expansion, and safely hyphens unpronounceable acronyms (e.g., `AWS` → `A-W-S`).
3. **`chunk_split(text, max_chars)`** — Splits text into TTS-safe chunks using NLTK (`sent_tokenize`). If a sentence exceeds the limit, it performs prosody-aware splitting at natural boundaries (commas, semicolons, em-dashes).

#### 3d — TTS Synthesis (`tts.synthesize` + cache)

For each chunk:
1. The `TTSProvider` instance handles pronunciation lexicons (currently via software fallback before API invocation).
2. If diarization is active, the pipeline assigns a deterministic distinct voice based on a hash of the speaker's name.
3. A cache key is computed from `provider + voice + format + text + lex_hash` (SHA-256, first 24 hex chars).
4. If `.cache/audiobooks/<key>.mp3` exists → cache hit, reads bytes from disk.
5. Otherwise → calls the TTS API, writes bytes to cache, returns bytes.

This cache means re-running the pipeline after a crash is fast — only uncached chunks hit the network. Updates to the `audiobook_lexicon.json` will also correctly invalidate the cache.

#### 3e — Stitching (`stitch.py`)

1. **`build_chapter(chunks, cfg)`** — Converts each raw-bytes chunk into a `pydub.AudioSegment`. Concatenates them with a configurable silence gap (default: 220ms) between chunks.
2. **`export_segment(seg, path)`** — Saves the chapter audio to disk as `outputs/audiobooks/<episode-id>/ch01.mp3`, `ch02.mp3`, etc.
3. **`export_book(chapters, cfg, out_path)`** — Concatenates all chapter segments with a larger silence gap (default: 700ms) between chapters. Runs `normalize_loudness()` targeting −20 dBFS. Saves the final file as `outputs/audiobooks/<episode-id>/<Episode Title>.mp3`.

---

### Step 4 — Supabase Upload (`storage.py`)

If `SUPABASE_URL` and `SUPABASE_KEY` are set:
- POSTs the MP3 file to `<SUPABASE_URL>/storage/v1/object/audiobooks/<Playlist Title>/<Episode Title>.mp3`.
- If a duplicate is detected (HTTP 400), retries with PUT to overwrite.
- Returns the public URL on success; returns `None` and logs a warning on failure.

The curator uses the public URL as `audio_url` if the upload succeeded, otherwise falls back to the local absolute path.

---

### Step 5 — Database Persistence (`playlist_service.py`)

All DB operations use SQLAlchemy sessions via `get_session()` context manager.

Key methods:

| Method | What it does |
|---|---|
| `find_or_create_playlist(slug, title, ...)` | Upsert by slug. Returns existing playlist or creates a new one in `draft` status. |
| `find_or_create_episode(playlist_id, title, seq_num, ...)` | Upsert by `(playlist_id, sequence_number)`. Returns existing or creates new in `pending` status. |
| `update_episode(episode_id, updates)` | Sets arbitrary fields (status, audio_url, duration_seconds, chapters, etc.). |
| `refresh_playlist_stats(playlist_id)` | Recomputes `episode_count` and `total_duration_seconds` from all `completed` episodes and writes them to the playlist row. |

---

## Configuration Reference

**`app/services/audiobook_config.yaml`**

```yaml
llm:
  provider: openai
  model: gpt-4.1
  temperature: 0.3
  max_words_per_request: 2500   # split long input before sending to LLM

tts:
  provider: deepgram            # deepgram | smallest
  voices:
    deepgram: aura-2-thalia-en
    smallest: meher
  models:
    smallest: lightning_v3.1_pro
  max_chars:
    deepgram: 1900              # per-request character cap
    smallest: 240
  speed: 1.0
  format: mp3

audio:
  silence_ms_between_chunks: 220
  silence_ms_between_chapters: 700
  target_dbfs: -20.0            # loudness normalization target
```

**`app/services/audiobook_lexicon.json`**

A flat JSON object mapping terms to their spoken equivalents:

```json
{
  "_comment": "Key = term to match (case-insensitive), Value = replacement",
  "UTXO": "you-tee-ex-oh",
  "BIP": "bitcoin improvement proposal",
  "DeFi": "dee-fye"
}
```

Keys starting with `_` are ignored (used for comments).

---

## Idempotency & Re-run Safety

The pipeline is designed to be safely re-run at any time:

- **Playlist** → matched by `slug`. If it exists, it is reused — never duplicated.
- **Episode** → matched by `(playlist_id, sequence_number)`. If it exists, it is reused.
- **`completed` episodes** → skipped in `_generate_and_update`. No TTS calls made.
- **`pending` / `failed` episodes** → re-attempted.
- **TTS cache** → chunk bytes cached by content hash. Unchanged text costs zero API calls.

This means you can safely run `python curate_audiobooks.py` multiple times and only genuinely new or failed work will be processed.
