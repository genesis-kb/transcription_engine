"""Regression tests for the audiobook pipeline (R1–R8).

Guards against known risk points discovered during code review.
"""

import io
from pathlib import Path
from unittest import mock

import pytest
from pydub import AudioSegment

from app.services.audiobook.ingestion import parse_file
from app.services.audiobook.pipeline import AudioPipeline
from app.services.audiobook.tts import make_provider


def _silent_mp3(duration_ms=200):
    seg = AudioSegment.silent(duration=duration_ms)
    buf = io.BytesIO()
    seg.export(buf, format="mp3")
    return buf.getvalue()


# ── R1: Ingestion dead-code branch — unknown type returns None ───────

class TestR1IngestionUnknownType:
    def test_invalid_type_returns_none(self, tmp_dir):
        f = tmp_dir / "bad_type.txt"
        f.write_text("---\ntype: podcast\ntitle: X\n---\nBody text.")
        assert parse_file(f) is None


# ── R2: Pipeline handles LLM returning chapters as non-list ──────────
# BUG: pipeline.py L135 does `if not chapters` but a non-empty string
# is truthy, so iteration proceeds over characters → crash.
# This test documents the bug; update when fixed.

class TestR2LLMBadChaptersShape:
    @mock.patch("app.services.audiobook.pipeline.make_provider")
    @mock.patch("app.services.audiobook.pipeline.rewrite")
    def test_chapters_as_string_crashes(self, mock_rw, mock_make, sample_cfg, tmp_dir):
        prov = mock.MagicMock()
        prov.name = "deepgram"
        prov.voice = "test"
        prov.fmt = "mp3"
        prov.synthesize.return_value = _silent_mp3()
        prov.lexicon = {}
        prov.apply_lexicon_fallback.side_effect = lambda t: t
        mock_make.return_value = prov

        mock_rw.return_value = {"title": "T", "chapters": "not-a-list"}

        pipeline = AudioPipeline(cfg=sample_cfg, lexicon={})
        with pytest.raises(TypeError):
            pipeline.generate_episode(
                text="Hello.", title="R2", output_dir=tmp_dir / "out", skip_llm=False,
            )


# ── R3: Curator skips completed episodes (idempotency) ───────────────

class TestR3IdempotencySkip:
    def test_completed_episode_skipped(self):
        from app.services.audiobook.curator import AudiobookCurator

        curator = AudiobookCurator.__new__(AudiobookCurator)
        curator._pipeline = mock.MagicMock()
        curator._playlists = mock.MagicMock()
        curator._provider_override = None
        curator._diarize = False

        episode = {"id": "ep-1", "title": "Done", "status": "completed"}
        result = curator._generate_and_update(episode, "text", skip_llm=True)

        assert result is False
        curator._pipeline.generate_episode.assert_not_called()


# ── R4: Failed episode marked as "failed", exception re-raised ───────

class TestR4FailedStatus:
    def test_failure_marks_status_and_reraises(self):
        from app.services.audiobook.curator import AudiobookCurator

        curator = AudiobookCurator.__new__(AudiobookCurator)
        curator._pipeline = mock.MagicMock()
        curator._pipeline.generate_episode.side_effect = RuntimeError("TTS boom")
        curator._pipeline.cfg = {"paths": {}}
        curator._playlists = mock.MagicMock()
        curator._provider_override = None
        curator._diarize = False

        episode = {"id": "ep-2", "title": "Fail", "status": "pending", "playlist_id": "pl-1"}

        with pytest.raises(RuntimeError, match="TTS boom"):
            curator._generate_and_update(episode, "text", skip_llm=True)

        curator._playlists.update_episode.assert_any_call("ep-2", {"status": "failed"})


# ── R5: Stitch normalizes mismatched sample rates ─────────────────────

class TestR5MismatchedSampleRates:
    def test_output_uses_first_chunk_rate(self):
        from app.services.audiobook.stitch import build_chapter

        def _make_chunk(rate):
            seg = AudioSegment.silent(duration=300, frame_rate=rate)
            buf = io.BytesIO()
            seg.export(buf, format="mp3")
            return buf.getvalue()

        cfg = {"tts": {"format": "mp3"}, "audio": {"silence_ms_between_chunks": 100}}
        chunks = [_make_chunk(44100), _make_chunk(22050)]
        result = build_chapter(chunks, cfg)
        assert result.frame_rate == 44100


# ── R6: Voice consistency across diarized chapters ────────────────────

class TestR6VoiceConsistency:
    @mock.patch("app.services.audiobook.pipeline.make_provider")
    def test_same_speaker_same_voice_across_chunks(self, mock_make, sample_cfg, tmp_dir):
        voices_used = []

        prov = mock.MagicMock()
        prov.name = "deepgram"
        prov.fmt = "mp3"
        prov.lexicon = {}
        prov.apply_lexicon_fallback.side_effect = lambda t: t

        # Track voice value at each synthesize call
        _voice = "default-voice"

        def _get_voice():
            return _voice

        def _set_voice(v):
            nonlocal _voice
            _voice = v

        type(prov).voice = property(lambda self: _get_voice(), lambda self, v: _set_voice(v))

        def _synth(text):
            voices_used.append(_voice)
            return _silent_mp3()

        prov.synthesize.side_effect = _synth
        mock_make.return_value = prov

        sample_cfg["paths"]["cache_dir"] = str(tmp_dir / "cache")
        pipeline = AudioPipeline(cfg=sample_cfg, lexicon={})

        text = (
            "Alice: Hello there.\n"
            "Bob: Hi Alice.\n"
            "Alice: Goodbye."
        )

        pipeline.generate_episode(
            text=text, title="R6", output_dir=tmp_dir / "out",
            skip_llm=False, diarize=True,
        )

        # Alice should get the same voice in chunks 1 and 3
        # Bob gets a different voice in chunk 2
        assert len(voices_used) >= 3
        assert voices_used[0] == voices_used[2] # Alice
        assert voices_used[0] != voices_used[1] # Alice vs Bob


# ── R7: normalize() graceful when num2words is absent ─────────────────

class TestR7Num2wordsMissing:
    def test_normalize_without_num2words(self):
        import app.services.audiobook.textproc as tp
        original = tp.num2words
        try:
            tp.num2words = None
            result = tp.normalize("21st century")
            assert "21st" in result
        finally:
            tp.num2words = original


# ── R8: make_provider raises on empty API key ─────────────────────────

class TestR8EmptyApiKey:
    def test_empty_key_raises(self, sample_cfg):
        sample_cfg["keys"]["deepgram"] = ""
        with pytest.raises(ValueError, match="Missing API key"):
            make_provider(sample_cfg)
