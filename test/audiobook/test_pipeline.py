"""Tests for app.services.audiobook.pipeline — Groups 10-11."""

import io
from unittest import mock

import pytest
from pydub import AudioSegment

from app.services.audiobook.pipeline import _cache_key, AudioPipeline, GeneratedEpisode


# ── Group 10: _cache_key ─────────────────────────────────────────────

class TestCacheKey:
    def test_deterministic(self):
        a = _cache_key("dg", "voice", "mp3", "hello")
        b = _cache_key("dg", "voice", "mp3", "hello")
        assert a == b

    def test_different_text(self):
        a = _cache_key("dg", "voice", "mp3", "hello")
        b = _cache_key("dg", "voice", "mp3", "world")
        assert a != b

    def test_different_provider(self):
        a = _cache_key("dg", "voice", "mp3", "hello")
        b = _cache_key("sm", "voice", "mp3", "hello")
        assert a != b

    def test_different_voice(self):
        a = _cache_key("dg", "v1", "mp3", "hello")
        b = _cache_key("dg", "v2", "mp3", "hello")
        assert a != b

    def test_different_speed(self):
        a = _cache_key("dg", "v", "mp3", "hello", speed=1.0)
        b = _cache_key("dg", "v", "mp3", "hello", speed=1.5)
        assert a != b

    def test_key_length(self):
        key = _cache_key("dg", "voice", "mp3", "text")
        assert len(key) == 24


# ── Group 11: AudioPipeline.generate_episode (mocked TTS) ───────────

def _silent_mp3(duration_ms=200):
    seg = AudioSegment.silent(duration=duration_ms)
    buf = io.BytesIO()
    seg.export(buf, format="mp3")
    return buf.getvalue()


def _mock_provider(duration_ms=200):
    p = mock.MagicMock()
    p.name = "deepgram"
    p.voice = "test"
    p.fmt = "mp3"
    p.synthesize.return_value = _silent_mp3(duration_ms)
    p.lexicon = {}
    p.apply_lexicon_fallback.side_effect = lambda t: t
    return p


class TestGenerateEpisode:
    @pytest.fixture
    def pipeline(self, sample_cfg):
        return AudioPipeline(cfg=sample_cfg, lexicon={})

    @mock.patch("app.services.audiobook.pipeline.make_provider")
    def test_skip_llm_no_rewrite_call(self, mock_make, pipeline, tmp_dir):
        mock_make.return_value = _mock_provider()
        with mock.patch("app.services.audiobook.pipeline.rewrite") as mock_rw:
            result = pipeline.generate_episode(
                text="Hello world.",
                title="Test",
                output_dir=tmp_dir / "out",
                skip_llm=True,
            )
            mock_rw.assert_not_called()
        assert isinstance(result, GeneratedEpisode)

    @mock.patch("app.services.audiobook.pipeline.make_provider")
    @mock.patch("app.services.audiobook.pipeline.rewrite")
    def test_llm_empty_chapters_fallback(self, mock_rw, mock_make, pipeline, tmp_dir):
        mock_make.return_value = _mock_provider()
        mock_rw.return_value = {"title": "T", "chapters": []}
        result = pipeline.generate_episode(
            text="Hello world.",
            title="Fallback",
            output_dir=tmp_dir / "out",
            skip_llm=False,
        )
        assert len(result.chapters) == 1

    @mock.patch("app.services.audiobook.pipeline.make_provider")
    def test_output_file_exists(self, mock_make, pipeline, tmp_dir):
        mock_make.return_value = _mock_provider()
        result = pipeline.generate_episode(
            text="Test.", title="Output", output_dir=tmp_dir / "out", skip_llm=True,
        )
        assert result.audio_path.exists()

    @mock.patch("app.services.audiobook.pipeline.make_provider")
    def test_duration_positive(self, mock_make, pipeline, tmp_dir):
        mock_make.return_value = _mock_provider(1000)
        result = pipeline.generate_episode(
            text="Test.", title="Dur", output_dir=tmp_dir / "out", skip_llm=True,
        )
        assert result.duration_seconds >= 1

    @mock.patch("app.services.audiobook.pipeline.make_provider")
    def test_special_chars_in_title(self, mock_make, pipeline, tmp_dir):
        mock_make.return_value = _mock_provider()
        result = pipeline.generate_episode(
            text="Test.", title='Hello/World: "Test"', output_dir=tmp_dir / "out", skip_llm=True,
        )
        assert result.audio_path.exists()

    @mock.patch("app.services.audiobook.pipeline.make_provider")
    def test_cache_hit_skips_synthesize(self, mock_make, pipeline, tmp_dir):
        prov = _mock_provider()
        mock_make.return_value = prov

        cache_dir = tmp_dir / "cache"
        pipeline.cfg["paths"]["cache_dir"] = str(cache_dir)

        # First run
        pipeline.generate_episode(
            text="Cached.", title="C1", output_dir=tmp_dir / "o1", skip_llm=True,
        )

        # Second run — same text, should hit cache
        prov.synthesize.reset_mock()
        pipeline.generate_episode(
            text="Cached.", title="C2", output_dir=tmp_dir / "o2", skip_llm=True,
        )
        assert prov.synthesize.call_count == 0
