"""Tests for app.services.audiobook.stitch — Group 9."""

import io
from pathlib import Path

import pytest
from pydub import AudioSegment

from app.services.audiobook.stitch import (
    build_chapter,
    export_book,
    export_segment,
    normalize_loudness,
)


def _make_audio_bytes(duration_ms=500, fmt="mp3", frame_rate=44100):
    seg = AudioSegment.silent(duration=duration_ms, frame_rate=frame_rate)
    buf = io.BytesIO()
    seg.export(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def stitch_cfg():
    return {
        "tts": {"format": "mp3"},
        "audio": {
            "silence_ms_between_chunks": 200,
            "silence_ms_between_chapters": 500,
            "target_dbfs": -20.0,
        },
    }


class TestBuildChapter:
    def test_empty_chunks(self, stitch_cfg):
        seg = build_chapter([], stitch_cfg)
        assert len(seg) == 0

    def test_single_chunk(self, stitch_cfg):
        chunk = _make_audio_bytes(500)
        seg = build_chapter([chunk], stitch_cfg)
        assert len(seg) > 0

    def test_multiple_chunks_have_gaps(self, stitch_cfg):
        chunks = [_make_audio_bytes(300), _make_audio_bytes(300)]
        seg = build_chapter(chunks, stitch_cfg)
        # Two 300ms chunks + 200ms gap = at least 800ms
        assert len(seg) >= 800


class TestExportBook:
    def test_creates_parent_dirs(self, tmp_dir, stitch_cfg):
        seg = AudioSegment.silent(duration=500)
        out = tmp_dir / "deep" / "nested" / "book.mp3"
        export_book([seg], stitch_cfg, out)
        assert out.exists()

    def test_empty_chapters(self, tmp_dir, stitch_cfg):
        out = tmp_dir / "empty.mp3"
        export_book([], stitch_cfg, out)
        assert out.exists()


class TestNormalizeLoudness:
    def test_silent_audio_no_crash(self):
        seg = AudioSegment.silent(duration=100)
        result = normalize_loudness(seg, -20.0)
        assert result is not None
