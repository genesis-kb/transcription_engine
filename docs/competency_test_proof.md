# Automated Ingestion Pipeline - Competency Test Proof

This document outlines the end-to-end process used to successfully execute the automated YouTube ingestion and transcription pipeline. It demonstrates the ability to seed specific channels, automatically fetch their latest videos, process them through the transcription engine, and apply LLM-based correction and summarization.

## 1. Objective
To automate the transcription workflow by taking a list of seeded YouTube channels, extracting the first/latest video from each, and passing it through the full transcription, correction, and summarization pipeline without manual intervention.

---

## 2. Execution Process

### Step 2.1: Seeding YouTube Channels
To begin, we decided on a set of target YouTube channels to monitor. We used the `venv/bin/python scripts/seed_channels.py` script to inject these channels into the database via the `/ingestion/channels` API endpoint.

**Channels Seeded:**
- Advancing Bitcoin
- TABConf
- Hodl Hodl

### Step 2.2: Starting the Backend Server
The transcription backend was started locally using Uvicorn to handle the incoming ingestion and transcription requests:
```bash
source venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8000
```

### Step 2.3: Running the Automated Pipeline
With the channels seeded and the server running, we executed the end-to-end automation script `venv/bin/python scripts/test_pipeline.py`. 

This script sequentially triggered the following automated steps:
1. **Channel Scanning (`/ingestion/run`)**: The pipeline scanned the seeded channels, fetched the single most recent video from each, and automatically approved them for transcription (bypassing the manual LLM classification phase).
2. **Queueing**: The approved videos were automatically pushed into the transcription queue with the necessary configuration flags enabled (`correct: True`, `summarize: True`, `llm_provider: "google"`).
3. **Processing (`/transcription/start/`)**: The transcription engine was instructed to begin processing the queue.

### Step 2.4: Transcription, Correction, and Summarization
As the queue was processed, the engine performed the following actions for each video:
1. **Transcription**: Generated the raw transcript using the configured local speech-to-text models.
2. **Correction**: Passed the raw text to the Google Gemini API to fix ASR mishears, typos, and technical jargon while preserving the original structure.
3. **Summarization**: Passed the corrected text to the Google Gemini API to generate a concise summary of the key points discussed in the video.

---

## 3. Proof of Execution

Below are screenshots demonstrating the successful execution of the pipeline, including the corrected transcripts and generated summaries.

> [!NOTE]
> *(Paste screenshots of the terminal output showing the corrected text and summaries from `test_pipeline.py`, or screenshots of the database/API responses here).*

### Corrected Transcriptions
*(Insert Screenshot Here)*

### Generated Summaries
*(Insert Screenshot Here)*
