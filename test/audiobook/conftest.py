"""Shared fixtures for audiobook tests."""

import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def tmp_dir():
    """Temporary directory cleaned up after each test."""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_cfg(tmp_dir):
    """Minimal pipeline config dict matching audiobook_config.yaml shape."""
    return {
        "tts": {
            "provider": "deepgram",
            "voices": {"deepgram": "aura-2-thalia-en", "smallest": "meher"},
            "models": {"smallest": "lightning_v3.1_pro"},
            "max_chars": {"deepgram": 1900, "smallest": 240},
            "speed": 1.0,
            "format": "mp3",
        },
        "llm": {
            "model": "gpt-4.1",
            "temperature": 0.3,
            "max_words_per_request": 3000,
        },
        "audio": {
            "silence_ms_between_chunks": 220,
            "silence_ms_between_chapters": 700,
            "target_dbfs": -20.0,
        },
        "paths": {
            "output_dir": str(tmp_dir / "outputs" / "audiobooks"),
            "cache_dir": str(tmp_dir / ".cache" / "audiobooks"),
        },
        "keys": {
            "openai": "test-openai-key",
            "deepgram": "test-deepgram-key",
            "smallest": "test-smallest-key",
        },
    }
