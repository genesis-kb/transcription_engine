"""Audiobook curation pipeline.

Modules:
    pipeline        — Core audio generation engine (text → MP3)
    ingestion       — Input file parser (YAML frontmatter)
    playlist_service — DB CRUD for playlists and episodes
    curator         — Orchestrator that wires everything together
    config          — Configuration loader
    textproc        — Text cleaning, normalization, chunking
    rewrite         — LLM chapterization via OpenAI
    tts             — TTS provider abstractions (Deepgram, Smallest)
    stitch          — Audio stitching and loudness normalization
"""
from .pipeline import AudiobookService, AudioPipeline
from .curator import AudiobookCurator
from .playlist_service import PlaylistService

__all__ = [
    "AudiobookService",
    "AudioPipeline",
    "AudiobookCurator",
    "PlaylistService",
]
