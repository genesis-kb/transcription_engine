# Transcription Engine — Complete API Reference

**Base URL**: `http://localhost:8000`

All endpoints are prefixed by their respective router. The four routers and their prefixes are:

| Router | Prefix |
|---|---|
| Ingestion | `/ingestion` |
| Transcription | `/transcription` |
| Curator | `/curator` |
| Media | `/media` |

---

## 1. Ingestion Router — `/ingestion`

### 1.1 Pipeline Orchestration

---

#### `POST /ingestion/run`

Runs the full ingestion pipeline in sequence: **scan → classify → queue**.

- **Body**: None
- **Response**:
  ```json
  {
    "status": "success",
    "scan": { "items_discovered": 5, "errors": [] },
    "classify": { "items_classified": 5, "items_approved": 3, "items_rejected": 2, "errors": [] },
    "queue": { "items_queued": 3, "errors": [] }
  }
  ```

---

#### `POST /ingestion/scan`

Triggers a scan of **all** active content sources for new items.

- **Body**: None
- **Response**:
  ```json
  {
    "status": "success",
    "items_discovered": 12,
    "errors": []
  }
  ```

---

#### `POST /ingestion/scan/{source_id}`

Triggers a scan for a **specific** source by its database UUID.

- **Path Parameter**: `source_id` — UUID of the source in `content_sources`
- **Body**: None
- **Success Response**:
  ```json
  {
    "status": "success",
    "items_discovered": 3,
    "errors": []
  }
  ```
- **Error Response** (`404`): Source not found or is not a YouTube source.

---

#### `POST /ingestion/classify`

Classifies **all pending** items using the configured LLM (Gemini).

- **Body**: None
- **Response**:
  ```json
  {
    "status": "success",
    "items_classified": 10,
    "items_approved": 7,
    "items_rejected": 3,
    "errors": []
  }
  ```

---

#### `POST /ingestion/classify/{item_id}`

Classifies a **single specific item** by its database UUID.

- **Path Parameter**: `item_id` — UUID of the item in `content_items`
- **Body**: None
- **Success Response**:
  ```json
  {
    "status": "success",
    "is_technical": true,
    "confidence": 0.92,
    "reason": "Conference talk on Bitcoin protocol internals."
  }
  ```
- **Error Response** (`404`): Item not found.
- **Error Response** (`500`): LLM classification failed.

---

### 1.2 Content Sources Management

---

#### `GET /ingestion/sources`

Lists **all** monitored content sources.

- **Query Parameters**: None
- **Response**:
  ```json
  {
    "data": [
      {
        "id": "uuid",
        "name": "Bitcoin Magazine",
        "slug": "bitcoin-magazine",
        "source_type": "youtube",
        "base_url": "https://www.youtube.com/@BitcoinMagazine",
        "config": { "yt_channel_id": "UCpXY...", "priority": 1 },
        "is_active": true,
        "last_run_status": "success",
        "last_run_id": "uuid",
        "created_at": "2026-05-01T10:00:00Z"
      }
    ]
  }
  ```

---

#### `POST /ingestion/sources`

Adds a **new** content source to monitor.

- **Body** (JSON):
  ```json
  {
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
  }
  ```
- **Required Fields**: `name`, `slug`
- **Optional Fields**: `source_type` (default: `youtube`), `base_url`, `config`, `is_active` (default: `true`)
- **Success Response** (`200`): The created `ContentSource` object.
- **Error Response** (`500`): Failed to add source.

---

#### `PUT /ingestion/sources/{source_id}`

Updates a monitored content source. Only the fields provided are updated.

- **Path Parameter**: `source_id` — UUID of the source
- **Body** (JSON, all fields optional):
  ```json
  {
    "name": "Updated Name",
    "is_active": false,
    "config": { "priority": 2 }
  }
  ```
- **Success Response** (`200`): The updated `ContentSource` object.
- **Error Response** (`400`): No fields provided to update.
- **Error Response** (`404`): Source not found.

---

#### `DELETE /ingestion/sources/{source_id}`

Removes a content source from monitoring.

- **Path Parameter**: `source_id` — UUID of the source
- **Body**: None
- **Success Response**:
  ```json
  { "status": "success", "message": "Source deleted." }
  ```
- **Error Response** (`404`): Source not found or delete failed.

---

### 1.3 Content Items Management

---

#### `GET /ingestion/items`

Lists all discovered content items with optional filtering and pagination.

- **Query Parameters**:

  | Parameter | Type | Default | Description |
  |---|---|---|---|
  | `status` | string | `null` | Filter by status: `pending`, `classified`, `queued`, `in_queue`, `transcribed`, `skipped` |
  | `is_technical` | boolean | `null` | `true` maps to `technical_score >= 4`, `false` maps to `technical_score < 4` |
  | `source_id` | UUID | `null` | Filter by a specific source |
  | `limit` | int | `100` | Max results to return |
  | `offset` | int | `0` | Pagination offset |

- **Response**:
  ```json
  {
    "data": [
      {
        "id": "uuid",
        "source_id": "uuid",
        "external_id": "dQw4w9WgXcQ",
        "title": "Bitcoin Script Deep Dive",
        "description": "...",
        "content_type": "video",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "published_at": "2026-04-01T12:00:00Z",
        "status": "queued",
        "technical_score": 5,
        "source_metadata": {
          "duration": 3600,
          "tags": ["bitcoin", "script"],
          "thumbnail_url": "...",
          "view_count": 15000,
          "classification_reason": "Technical deep-dive on Bitcoin scripting.",
          "classification_confidence": 0.95
        },
        "discovered_at": "2026-05-20T08:00:00Z"
      }
    ]
  }
  ```

---

#### `PUT /ingestion/items/{item_id}`

Manually **approve or reject** an item, overriding the LLM classification.

- **Path Parameter**: `item_id` — UUID of the item
- **Body** (JSON):
  ```json
  {
    "is_technical": true,
    "classification_reason": "Manually approved — conference keynote."
  }
  ```
- **Logic**:
  - `is_technical: true` → sets `technical_score = 5`, `status = "queued"`
  - `is_technical: false` → sets `technical_score = 1`, `status = "skipped"`
  - The `classification_reason` is stored inside `source_metadata.classification_reason`
- **Success Response** (`200`): The updated `ContentItem` object.
- **Error Response** (`404`): Item not found.

---

### 1.4 Audit Logs

---

#### `GET /ingestion/runs`

Lists the history of all pipeline runs for auditing purposes.

- **Query Parameters**:

  | Parameter | Type | Default | Description |
  |---|---|---|---|
  | `limit` | int | `50` | Max number of runs to return |

- **Response**:
  ```json
  {
    "data": [
      {
        "id": "uuid",
        "source_id": "uuid",
        "started_at": "2026-05-20T08:00:00Z",
        "completed_at": "2026-05-20T08:05:30Z",
        "status": "success"
      }
    ]
  }
  ```

---

## 2. Transcription Router — `/transcription`

### 2.1 Queue Management

---

#### `POST /transcription/add_to_queue/`

Adds a new source to the transcription queue.

- **Body** (multipart form-data):

  | Field | Type | Default | Description |
  |---|---|---|---|
  | `source` | string | — | YouTube URL or file path |
  | `source_file` | file | — | Upload a JSON file with sources |
  | `loc` | string | `misc` | Location / category slug |
  | `model` | string | `tiny.en` | Local Whisper model to use |
  | `title` | string | `null` | Override title |
  | `date` | string | `null` | Override date |
  | `tags` | list | `[]` | Tags to attach |
  | `speakers` | list | `[]` | Speaker names |
  | `deepgram` | bool | `false` | Use Deepgram STT |
  | `smallestai` | bool | `false` | Use SmallestAI STT |
  | `diarize` | bool | `false` | Enable speaker diarization |
  | `markdown` | bool | `false` | Output as Markdown |
  | `correct` | bool | `false` | Run LLM correction |
  | `summarize` | bool | `false` | Generate summary |
  | `username` | string | `null` | Submitter username |
  | `upload` | bool | `false` | Upload to S3 |
  | `github` | bool | `false` | Push to GitHub |

- **Response**:
  ```json
  { "status": "queued", "message": "Transcription source has been added to the queue." }
  ```

---

#### `POST /transcription/remove_from_queue/`

Removes one or more sources from the queue using an uploaded JSON file.

- **Body** (multipart form-data): `source_file` (file, required)
- **Response**:
  ```json
  { "status": "success", "message": "Removed 2 sources from the queue." }
  ```

---

#### `POST /transcription/preprocess/`

Preprocesses a source (validates metadata) without adding it to the transcription queue.

- **Body** (multipart form-data): same fields as `add_to_queue/` (minus pipeline flags)
- **Response**:
  ```json
  { "status": "success", "data": [ { ... preprocessed source objects ... } ] }
  ```

---

#### `GET /transcription/queue/`

Returns all items currently in the transcription queue with their status.

- **Response**:
  ```json
  { "data": [ { "title": "...", "status": "queued", ... } ] }
  ```

---

### 2.2 Execution

---

#### `POST /transcription/start/`

Starts the transcription process for all queued items (runs in background).

- **Body**: None
- **Response**:
  ```json
  { "status": "started", "message": "Transcription process has started." }
  ```
- **Note**: Must be called with `POST`. A `GET` request returns `405 Method Not Allowed`.

---

### 2.3 In-Memory Results

---

#### `GET /transcription/corrected/`

Returns all transcripts that have been LLM-corrected from the current in-memory queue.

- **Response**:
  ```json
  { "data": [ { "title": "...", "corrected_text": "...", "status": "done" } ] }
  ```

---

#### `GET /transcription/summaries/`

Returns all transcripts that have an LLM-generated summary from the current in-memory queue.

- **Response**:
  ```json
  { "data": [ { "title": "...", "summary": "...", "status": "done" } ] }
  ```

---

### 2.4 Database-Backed Results

---

#### `GET /transcription/db/transcripts/`

Fetches all transcripts stored in the database with pagination.

- **Query Parameters**: `limit` (default: `50`), `offset` (default: `0`)
- **Response**: `{ "data": [ { ...Transcript objects... } ] }`

---

#### `GET /transcription/db/transcripts/{transcript_id}`

Fetches a single transcript by its database UUID.

- **Path Parameter**: `transcript_id`
- **Response**: `{ "data": { ...Transcript object... } }`
- **Error Response** (`404`): Transcript not found.

---

#### `GET /transcription/db/corrected/`

Fetches corrected transcripts from the database with pagination.

- **Query Parameters**: `limit` (default: `50`), `offset` (default: `0`)
- **Response**: `{ "data": [ { ...Transcript objects with corrected_text... } ] }`

---

#### `GET /transcription/db/summaries/`

Fetches transcript summaries from the database with pagination.

- **Query Parameters**: `limit` (default: `50`), `offset` (default: `0`)
- **Response**: `{ "data": [ { ...Summary objects... } ] }`

---

## 3. Curator Router — `/curator`

---

#### `POST /curator/get_sources/`

Fetches available transcription sources from the BTC Transcripts repository.

- **Body** (JSON):
  ```json
  {
    "loc": "all",
    "coverage": "none"
  }
  ```
  - `loc`: Location filter (e.g., `"all"`, `"conference/bitcoin-2023"`)
  - `coverage`: One of `"none"`, `"partial"`, `"full"`

- **Response**: `{ "status": "success", "data": [ ... ] }`

---

#### `POST /curator/get_transcription_backlog/`

Returns the full list of sources that have not yet been transcribed.

- **Body**: None
- **Response**: `{ "status": "success", "data": [ ... ] }`

---

## 4. Media Router — `/media`

---

#### `POST /media/youtube-video-url`

Extracts the direct streamable video URL from a YouTube link.

- **Body** (JSON):
  ```json
  { "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }
  ```
- **Success Response**:
  ```json
  { "status": "success", "video_url": "https://..." }
  ```
- **Error Response** (`500`): Could not extract the video URL.
