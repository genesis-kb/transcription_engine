# Local Run & Queue Guide

A step-by-step guide to run the project locally, initialize the database, and queue YouTube videos for transcription.

---

## Prerequisites

- Python 3.9+
- A running PostgreSQL database (e.g. [Supabase](https://supabase.com))
- A Google / YouTube API key

---

## 1. Clone the repository

```bash
git clone https://github.com/<your-username>/transcription_engine.git
cd transcription_engine
```

---

## 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3. Configure environment

```bash
cp env.example .env
```

Open `.env` and set at minimum:

```env
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/postgres?sslmode=require
GOOGLE_API_KEY=your_google_api_key
YOUTUBE_API_KEY=your_youtube_api_key
```

> **Tip:** If you are using the Supabase connection pooler, use the pooler hostname and include `sslmode=require`.

---

## 4. Initialize the database

The project does **not** auto-create tables on startup. Run this once after setting up your `.env`:

```bash
python -c "from dotenv import load_dotenv; load_dotenv(); from app.database import init_db; print(init_db())"
```

Expected output: `True`

---

## 5. Start the API server

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

---

## 6. Queue YouTube videos

Open a **second terminal** (with the virtual environment activated) and run:

```bash
curl -X POST http://localhost:8000/transcription/queue/ \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=<VIDEO_ID>"}'
```

Repeat for each video you want to queue. You can script this to queue multiple videos at once:

```bash
VIDEO_IDS=("id1" "id2" "id3")
for id in "${VIDEO_IDS[@]}"; do
  curl -X POST http://localhost:8000/transcription/queue/ \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"https://www.youtube.com/watch?v=${id}\"}"
done
```

---

## 7. Start processing the queue

```bash
curl -X POST http://localhost:8000/transcription/start/
```

> **Note:** This endpoint only accepts `POST`. A browser `GET` request will return `{"detail": "Method Not Allowed"}`.

---

## 8. Verify status and saved data

```bash
# Check the current queue
curl http://localhost:8000/transcription/queue/

# List saved transcripts
curl http://localhost:8000/transcription/db/transcripts/
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `No module named uvicorn` | Run `pip install -r requirements.txt` inside your virtual environment |
| `ImportError: cannot import name 'genai' from 'google'` | Ensure `google-genai` is listed in `requirements.txt` and reinstall |
| `DATABASE_URL not set` | Ensure `.env` exists and variables are exported; one-off commands need `load_dotenv()` |
| `Network is unreachable` (Supabase) | Use the Supabase **pooler** connection string and add `sslmode=require` |
