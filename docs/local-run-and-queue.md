# Local Run And Queue Guide

This runbook documents the exact flow to run the project locally, initialize the database, and queue 10 YouTube videos.

## 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
/home/parth/Cloned_repos/transcription_engine/venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000

## 2. Configure environment

```bash
cp env.example .env
```

Set at least these values in `.env`:

- `DATABASE_URL`
- `GOOGLE_API_KEY`
- `YOUTUBE_API_KEY`

Example (Supabase pooler):

```env
DATABASE_URL=postgresql://<user>:<password>@<pooler-host>:5432/postgres?sslmode=require
```

## 3. Create database tables

The project does not auto-create tables on startup. Run this once:

```bash
python -c "from dotenv import load_dotenv; load_dotenv(); from app.database import init_db; print(init_db())"
```

Expected result: `True`

## 4. Start API server

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

## 5. Queue 10 YouTube videos

Use this shell snippet from a second terminal:

```bash
home/parth/Cloned_repos/transcription_engine/venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

## 6. Start processing queue

```bash
curl -X POST http://localhost:8000/transcription/start/
```

Note: This endpoint is `POST`. Opening it in the browser (`GET`) returns `{"detail":"Method Not Allowed"}`.

## 7. Verify status and saved data

```bash
curl http://localhost:8000/transcription/queue/
curl http://localhost:8000/transcription/db/transcripts/
```

## Troubleshooting

- `No module named uvicorn`
  - Run: `pip install -r requirements.txt`
- `ImportError: cannot import name 'genai' from 'google'`
  - Ensure `google-genai` is installed from `requirements.txt`.
- `DATABASE_URL not set`
  - Ensure `.env` exists and load it in one-off commands with `load_dotenv()`.
- `Network is unreachable` to Supabase on direct host
  - Use Supabase pooler connection string and include `sslmode=require`.
