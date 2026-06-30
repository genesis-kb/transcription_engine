"""
Section 6 — Source Type Tests
===============================
Integration tests that exercise ``Transcription.add_transcription_source()``
with real source paths.  All tests run with ``test_mode=True`` so no actual
ASR call is made.

Marks:
- ``integration`` — exercises real filesystem / source detection paths
- ``slow``        — YouTube tests that hit the network (skipped in CI by default)
"""

import os
import pytest

pytestmark = pytest.mark.integration


def _make_transcription(monkeypatch, tmp_config, **kwargs):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai", "nocheck": "True"})
    from app.transcription import Transcription
    return Transcription(test_mode=True, username="test_user", **kwargs)


# ---------------------------------------------------------------------------
# Local audio file
# ---------------------------------------------------------------------------

def test_local_audio_file_is_detected(test_audio_path, tmp_config, monkeypatch):
    """A local .mp3 file must be classified as an 'audio' source."""
    t = _make_transcription(monkeypatch, tmp_config)
    result = t.add_transcription_source(
        source_file=str(test_audio_path),
        title="Local Audio Test",
        nocheck=True,
    )
    assert len(t.transcripts) == 1
    assert t.transcripts[0].source.type == "audio"
    assert len(result["added"]) == 1


def test_local_audio_transcription_completes(test_audio_path, tmp_config, monkeypatch):
    """Full pipeline (test_mode) must reach 'completed' for a local audio file."""
    t = _make_transcription(monkeypatch, tmp_config)
    t.add_transcription_source(
        source_file=str(test_audio_path),
        title="Local Audio Pipeline Test",
        nocheck=True,
    )
    transcripts = t.start()
    assert len(transcripts) == 1
    assert transcripts[0].status == "completed"


def test_local_audio_raw_output_is_set(test_audio_path, tmp_config, monkeypatch):
    """In test_mode, outputs['raw'] must be set to a non-empty string after start()."""
    t = _make_transcription(monkeypatch, tmp_config)
    t.add_transcription_source(
        source_file=str(test_audio_path),
        title="Local Audio Output Test",
        nocheck=True,
    )
    t.start()
    assert t.transcripts[0].outputs.get("raw") not in (None, "")


# ---------------------------------------------------------------------------
# Duplicate source detection
# ---------------------------------------------------------------------------

def test_duplicate_source_raises(test_audio_path, tmp_config, monkeypatch):
    """Adding the same (loc, title) twice must raise DuplicateSourceError."""
    from app.exceptions import DuplicateSourceError

    t = _make_transcription(monkeypatch, tmp_config)
    t.add_transcription_source(
        source_file=str(test_audio_path),
        title="Duplicate Test",
        nocheck=True,
    )
    with pytest.raises(DuplicateSourceError):
        t.add_transcription_source(
            source_file=str(test_audio_path),
            title="Duplicate Test",
            nocheck=True,
        )


# ---------------------------------------------------------------------------
# YouTube (network — skipped in CI)
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_youtube_video_source_is_detected(tmp_config, monkeypatch):
    """A valid YouTube URL must be classified as a 'video' source."""
    # Use a short, freely available video; swap out if it gets deleted
    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    t = _make_transcription(monkeypatch, tmp_config)
    result = t.add_transcription_source(
        source_file=yt_url,
        title="YouTube Source Test",
        nocheck=True,
    )
    assert len(t.transcripts) >= 1
    assert t.transcripts[0].source.type == "video"
    assert len(result["added"]) >= 1
