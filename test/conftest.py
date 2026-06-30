"""
Shared pytest fixtures for the transcription engine test suite.

All fixtures here are available to every test file in tests/.
"""

import configparser
import os
import shutil
import tempfile

import pytest
from unittest.mock import MagicMock

from app.services.factory import reset_registry


# ---------------------------------------------------------------------------
# Registry management
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_registry():
    """Reset the ASR provider registry before and after every test."""
    reset_registry()
    yield
    reset_registry()


# ---------------------------------------------------------------------------
# Infrastructure stubs
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_data_writer():
    """Return a MagicMock that satisfies the DataWriter interface."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Test assets
# ---------------------------------------------------------------------------

TEST_AUDIO = os.path.join(
    os.path.dirname(__file__),
    "testAssets",
    "audio.mp3",
)


@pytest.fixture
def test_audio_path():
    """Absolute path to the bundled test audio file.

    The test is skipped if the asset is not present (e.g. in a minimal CI
    checkout that doesn't include large binary files).
    """
    if not os.path.exists(TEST_AUDIO):
        pytest.skip(f"Test asset not found: {TEST_AUDIO}")
    return TEST_AUDIO


# ---------------------------------------------------------------------------
# Config patching
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Write a temporary config.ini and patch ``settings.config`` to use it.

    Usage::

        def test_something(tmp_config):
            tmp_config({"asr_provider": "whisper", "summarize": "False"})
            # settings.config now reflects the overrides above
    """
    def _make(overrides: dict) -> str:
        config_path = tmp_path / "config.ini"
        parser = configparser.ConfigParser()
        parser["DEFAULT"] = overrides
        with open(config_path, "w") as fh:
            parser.write(fh)

        # Re-read the section so callers get a real SectionProxy (not a dict).
        fresh = configparser.ConfigParser()
        fresh.read(str(config_path))

        # Patch settings so the app code sees the test config.
        from app.config import settings
        monkeypatch.setattr(settings, "config", fresh["DEFAULT"])
        return str(config_path)

    return _make


# ---------------------------------------------------------------------------
# Common env-var helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def dummy_openai_key(monkeypatch):
    """Inject a dummy OPENAI_API_KEY so import-time key checks don't raise."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-openai")


@pytest.fixture
def dummy_deepgram_key(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-deepgram")


@pytest.fixture
def dummy_google_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-google")


@pytest.fixture
def dummy_claude_key(monkeypatch):
    monkeypatch.setenv("CLAUDE_API_KEY", "dummy-claude")


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir():
    """Create a temporary directory and clean it up after the test."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Additional test assets
# ---------------------------------------------------------------------------

TEST_VIDEO = os.path.join(
    os.path.dirname(__file__),
    "testAssets",
    "test_video.mp4",
)

PAYLOAD_JSON = os.path.join(
    os.path.dirname(__file__),
    "testAssets",
    "payload.json",
)

TRANSCRIPT_TXT = os.path.join(
    os.path.dirname(__file__),
    "testAssets",
    "transcript.txt",
)


@pytest.fixture
def test_video_path():
    """Absolute path to the bundled test video file (skipped if absent)."""
    if not os.path.exists(TEST_VIDEO):
        pytest.skip(f"Test asset not found: {TEST_VIDEO}")
    return TEST_VIDEO


@pytest.fixture
def transcript_txt_path():
    """Absolute path to the bundled transcript text file (skipped if absent)."""
    if not os.path.exists(TRANSCRIPT_TXT):
        pytest.skip(f"Test asset not found: {TRANSCRIPT_TXT}")
    return TRANSCRIPT_TXT


# ---------------------------------------------------------------------------
# Mock transcript (used by exporter tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_transcript():
    """A richly-configured MagicMock that satisfies the Transcript interface."""
    from app.transcript import Source, Transcript

    transcript = MagicMock(spec=Transcript)
    transcript.title = "Test Transcript"

    transcript.source = MagicMock(spec=Source)
    transcript.source.loc = "test/location"
    transcript.source.title = "Test Transcript"
    transcript.source.tags = ["tag1", "tag2"]
    transcript.source.category = ["category1"]
    transcript.source.speakers = ["Speaker 1"]
    transcript.source.type = "video"
    transcript.source.media = "http://example.com/video.mp4"
    transcript.source.to_json.return_value = {
        "title": "Test Transcript",
        "speakers": ["Speaker 1", "Speaker 2"],
        "tags": ["tag1", "tag2"],
        "type": "video",
        "loc": "test/location",
        "source_file": "http://example.com/video.mp4",
        "categories": ["category1", "category2"],
        "media": "http://example.com/video.mp4",
        "date": "2023-01-01",
        "chapters": [],
    }

    transcript.outputs = {
        "raw": "This is a test transcript.\n\nIt has multiple paragraphs.",
        "markdown": None,
        "json": None,
        "text": None,
    }

    transcript.to_json.return_value = {
        "title": "Test Transcript",
        "speakers": ["Speaker 1", "Speaker 2"],
        "tags": ["tag1", "tag2"],
        "categories": ["category1", "category2"],
        "loc": "test/location",
        "body": "This is a test transcript.\n\nIt has multiple paragraphs.",
    }

    return transcript


# ---------------------------------------------------------------------------
# Exporter fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def markdown_exporter(temp_dir):
    """MarkdownExporter pointed at a temp directory."""
    from app.exporters import MarkdownExporter
    return MarkdownExporter(temp_dir, transcript_by="Test User")


@pytest.fixture
def json_exporter(temp_dir):
    """JsonExporter pointed at a temp directory."""
    from app.exporters import JsonExporter
    return JsonExporter(temp_dir, transcript_by="Test User")


@pytest.fixture
def text_exporter(temp_dir):
    """TextExporter pointed at a temp directory."""
    from app.exporters import TextExporter
    return TextExporter(temp_dir)

