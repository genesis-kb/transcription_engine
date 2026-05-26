# API Examples and Testing Guide

This document provides `curl` commands to test the endpoints in the Transcription Engine API.
You can run these commands in your terminal while the server is running on `http://localhost:8000`.

## 1. Ingestion Endpoints (`/ingestion`)

### 1.1 Content Sources Management

**List Sources**
```bash
curl -X GET http://localhost:8000/ingestion/sources
```

**Add a New Source**
```bash
curl -X POST http://localhost:8000/ingestion/sources \
     -H "Content-Type: application/json" \
     -d '{
           "name": "Test Channel",
           "slug": "test-channel",
           "source_type": "youtube",
           "base_url": "https://www.youtube.com/@TestChannel",
           "config": {"yt_channel_id": "UC123456789", "priority": 1},
           "is_active": true
         }'
```

**Update a Source**
*(Replace `SOURCE_ID` with the ID returned from the add command)*
```bash
curl -X PUT http://localhost:8000/ingestion/sources/SOURCE_ID \
     -H "Content-Type: application/json" \
     -d '{"is_active": false}'
```

**Delete a Source**
*(Replace `SOURCE_ID` with the ID from above)*
```bash
curl -X DELETE http://localhost:8000/ingestion/sources/SOURCE_ID
```

### 1.2 Pipeline Orchestration

**Scan All Sources**
```bash
curl -X POST http://localhost:8000/ingestion/scan
```

**Classify Pending Items**
```bash
curl -X POST http://localhost:8000/ingestion/classify
```

**Run Full Pipeline (Scan -> Classify -> Queue)**
```bash
curl -X POST http://localhost:8000/ingestion/run
```

### 1.3 Content Items Management

**List Items**
```bash
curl -X GET http://localhost:8000/ingestion/items?limit=5
```

**Manually Approve an Item**
*(Replace `ITEM_ID` with a valid item ID)*
```bash
curl -X PUT http://localhost:8000/ingestion/items/ITEM_ID \
     -H "Content-Type: application/json" \
     -d '{"is_technical": true, "classification_reason": "Manual test"}'
```

### 1.4 Audit Logs

**List Pipeline Runs**
```bash
curl -X GET http://localhost:8000/ingestion/runs?limit=5
```


## 2. Transcription Endpoints (`/transcription`)

**Add to Queue**
```bash
curl -X POST http://localhost:8000/transcription/add_to_queue/ \
     -F "source=https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
     -F "loc=misc" \
     -F "model=tiny.en"
```

**View Queue**
```bash
curl -X GET http://localhost:8000/transcription/queue/
```

**Start Transcription**
```bash
curl -X POST http://localhost:8000/transcription/start/
```

**Get Corrected Transcripts (In-Memory)**
```bash
curl -X GET http://localhost:8000/transcription/corrected/
```

**Get DB Transcripts**
```bash
curl -X GET http://localhost:8000/transcription/db/transcripts/?limit=5
```


## 3. Curator Endpoints (`/curator`)

**Get Sources**
```bash
curl -X POST http://localhost:8000/curator/get_sources/ \
     -H "Content-Type: application/json" \
     -d '{"loc": "all", "coverage": "none"}'
```

**Get Transcription Backlog**
```bash
curl -X POST http://localhost:8000/curator/get_transcription_backlog/
```


## 4. Media Endpoints (`/media`)

**Extract YouTube Video URL**
```bash
curl -X POST http://localhost:8000/media/youtube-video-url \
     -H "Content-Type: application/json" \
     -d '{"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```
