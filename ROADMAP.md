# BitScribe Roadmap

This is a living document. We update it as priorities shift based on feedback and production learnings. If something here excites you, open an issue or PR.

---

## In Progress

- [ ] **Transcript correction backfill** — run correction on all existing transcripts in RDS and verify quality
- [ ] **CI pipeline for transcription engine** — lint (ruff) + test (pytest) on push

## Next Up — Contributions Welcome

These are well-scoped and ready to build. Each builds directly on the existing codebase.

### Transcript Quality

- [ ] **Speaker identification** — map "Speaker 0/1/2" from diarization to actual names using YouTube metadata, conference schedules, and LLM inference.

### Ingestion

- [ ] **RSS feed poller** — monitor Bitcoin podcast RSS feeds (Stephan Livera, What Bitcoin Did, Bitcoin Audible) for new episodes, auto-queue for transcription
- [ ] **Job scheduler** — APScheduler or cron for recurring tasks (scan YouTube channels every 6h, poll RSS daily)

### Translation

- [ ] **LLM-based translation service** — chunked translation for long transcripts. Priority languages: Spanish, Portuguese, Japanese, Chinese, German
- [ ] **Translation storage** — `translations` table linked to original transcript, served via API

### Developer API

- [ ] **API key authentication** — FastAPI middleware for API key auth with rate limiting
- [ ] **Versioned public API** — `/api/v1/` routes with proper auth, pagination, and OpenAPI docs
- [ ] **Usage tracking** — log API calls per key for analytics

## Future

These are bigger bets we're exploring. Community input will shape what gets built.

### Podcast Generation

- [ ] **Podcast script generator** — input transcript IDs, LLM generates a podcast script with intro, topic segments, transitions, and outro. Configurable tone (casual/educational/technical)
- [ ] **Multi-voice TTS** — support multiple voices for multi-speaker podcasts, concatenate segments with chapter markers
- [ ] **Podcast API** — submit transcript IDs, get a generated audio file. Frontend page for selecting transcripts, previewing the script, and listening

### Analytics & Knowledge Graph

- [ ] **Analytics dashboard** — topic trends over time, speaker activity, conference stats, transcript volume growth
- [ ] **Knowledge graph** — extract entities and relationships from transcripts via LLM. Query: "Show me everything related to OP_VAULT" or "How are these speakers connected?"
- [ ] **Graph visualization** — interactive entity relationship explorer on the frontend
- [ ] **BIP/BOLT explainers** — ingest Bitcoin and Lightning specifications, match them to transcript context, and generate audience-specific explanations. See [BIP/BOLT Explainer Pipeline](docs/bip_bolt_explainer_pipeline.md).

---

## Architecture

```
YouTube / RSS / GitHub
        |
   [Ingestion] ---- ChannelScanner, ContentClassifier, RSSPoller
        |
   [Transcription] - Whisper / Deepgram / SmallestAI
        |
   [Post-Processing]
        |--- MetadataExtractor (speakers, conference, topics)
        |--- CorrectionService (fix ASR errors)
        |--- SummarizerService (structured summary)
        |--- SpeakerDetector (resolve Speaker 0 → real names) [planned]
        |--- ChapterGenerator (auto-generate chapters) [planned]
        |
   [Storage] ------- AWS RDS PostgreSQL + pgvector [planned]
        |
   [API] ----------- FastAPI (transcription engine)
        |            Express.js (frontend backend)
        |
   [Frontend] ------ React + Vite (GitHub Pages)
```
---

## How to Contribute

1. **Pick something from "Next Up"** — these are ready for PRs
2. **Check the [issues](https://github.com/genesis-kb/transcription_engine/issues)** — look for `good first issue` and `help wanted` labels
3. **Propose something new** — open an issue describing what you want to build
4. **Read the codebase** — start with `server.py`, then `app/transcription.py`, then `app/services/`

See [README.md](README.md) for setup instructions.
