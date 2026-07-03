"""Unit tests for the audiobook curation pipeline.

Covers: YAML frontmatter parsing, text normalization/chunking,
diarization parsing, rewrite validation, and audio stitching helpers.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on the path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)


# =========================================================================
# Ingestion — YAML frontmatter parsing
# =========================================================================


class TestIngestion:
    """Tests for app.services.audiobook.ingestion."""

    def test_parse_single_article_with_frontmatter(self, tmp_path):
        from app.services.audiobook.ingestion import parse_file

        f = tmp_path / "article.txt"
        f.write_text(
            "---\ntype: single_article\ntitle: Test Title\nauthor: Alice\n---\nHello world body text."
        )
        result = parse_file(f)
        assert result is not None
        assert result.input_type == "single_article"
        assert result.title == "Test Title"
        assert result.author == "Alice"
        assert "Hello world body text." in result.body

    def test_parse_plain_text_without_frontmatter(self, tmp_path):
        from app.services.audiobook.ingestion import parse_file

        f = tmp_path / "my-article.txt"
        f.write_text("Just plain text content without YAML.")
        result = parse_file(f)
        assert result is not None
        assert result.input_type == "single_article"
        assert result.title == "My Article"  # derived from filename

    def test_empty_file_returns_none(self, tmp_path):
        from app.services.audiobook.ingestion import parse_file

        f = tmp_path / "empty.txt"
        f.write_text("")
        result = parse_file(f)
        assert result is None

    def test_empty_body_with_frontmatter_returns_none(self, tmp_path):
        from app.services.audiobook.ingestion import parse_file

        f = tmp_path / "no-body.txt"
        f.write_text("---\ntitle: Only Header\n---\n")
        result = parse_file(f)
        assert result is None

    def test_non_mapping_frontmatter_treated_as_single_article(self, tmp_path):
        """Non-dict YAML (e.g. a bare string) should not crash."""
        from app.services.audiobook.ingestion import parse_file

        f = tmp_path / "bad-yaml.txt"
        f.write_text("---\njust a string\n---\nBody text here.")
        result = parse_file(f)
        assert result is not None
        assert result.input_type == "single_article"

    def test_series_missing_slug_returns_none(self, tmp_path):
        from app.services.audiobook.ingestion import parse_file

        f = tmp_path / "series.txt"
        f.write_text("---\ntype: series\ntitle: No Slug\n---\nSome body text.")
        result = parse_file(f)
        assert result is None

    def test_series_valid_parse(self, tmp_path):
        from app.services.audiobook.ingestion import parse_file

        f = tmp_path / "series.txt"
        f.write_text(
            "---\ntype: series\nseries_slug: my-series\n"
            "series_title: My Series\nsequence_number: 3\n"
            "title: Episode 3\n---\nSeries body text."
        )
        result = parse_file(f)
        assert result is not None
        assert result.input_type == "series"
        assert result.series_slug == "my-series"
        assert result.sequence_number == 3

    def test_scan_and_group_series(self, tmp_path):
        from app.services.audiobook.ingestion import (
            group_series,
            scan_input_directory,
        )

        for i in range(1, 4):
            (tmp_path / f"ep{i}.txt").write_text(
                f"---\ntype: series\nseries_slug: test-series\n"
                f"sequence_number: {i}\ntitle: Episode {i}\n---\nBody {i}."
            )
        inputs = scan_input_directory(tmp_path)
        assert len(inputs) == 3
        groups = group_series(inputs)
        assert "test-series" in groups
        assert len(groups["test-series"]) == 3
        # Should be sorted by sequence_number
        assert groups["test-series"][0].sequence_number == 1
        assert groups["test-series"][2].sequence_number == 3


# =========================================================================
# Text Processing — cleaning, normalization, chunking, diarization
# =========================================================================


class TestTextProc:
    """Tests for app.services.audiobook.textproc."""

    def test_clean_text_strips_timestamps(self):
        from app.services.audiobook.textproc import clean_text

        text = "[00:12:45] Hello there (1:30) world"
        result = clean_text(text)
        assert "[00:12:45]" not in result
        assert "(1:30)" not in result
        assert "Hello" in result

    def test_clean_text_strips_speaker_labels(self):
        from app.services.audiobook.textproc import clean_text

        text = "ALICE: Hello\nBOB: World"
        result = clean_text(text, retain_speakers=False)
        assert "ALICE:" not in result
        assert "BOB:" not in result

    def test_clean_text_retains_speakers(self):
        from app.services.audiobook.textproc import clean_text

        text = "ALICE: Hello\nBOB: World"
        result = clean_text(text, retain_speakers=True)
        assert "ALICE:" in result
        assert "BOB:" in result

    def test_clean_text_strips_stage_directions(self):
        from app.services.audiobook.textproc import clean_text

        text = "Hello [laughter] world (applause) end"
        result = clean_text(text)
        assert "[laughter]" not in result
        assert "(applause)" not in result

    def test_normalize_expands_money(self):
        from app.services.audiobook.textproc import normalize

        result = normalize("It costs $5k to run")
        assert "thousand" in result
        assert "dollars" in result

    def test_normalize_with_lexicon_overrides_acronyms(self):
        """Lexicon entries should take precedence over generic acronym expansion."""
        from app.services.audiobook.textproc import normalize

        lexicon = {"BTC": "bitcoin"}
        result = normalize("Buy BTC now", lexicon=lexicon)
        assert "bitcoin" in result
        # Should NOT have been expanded as B-T-C
        assert "B-T-C" not in result

    def test_normalize_without_lexicon_expands_acronyms(self):
        from app.services.audiobook.textproc import normalize

        result = normalize("Buy BTC now")
        assert "B-T-C" in result

    def test_normalize_preserves_pronounceable_acronyms(self):
        from app.services.audiobook.textproc import normalize

        result = normalize("NASA launched a rocket")
        assert "NASA" in result  # Should NOT be expanded

    def test_parse_diarization_no_speakers(self):
        from app.services.audiobook.textproc import parse_diarization

        chunks = parse_diarization("Just plain text here.")
        assert len(chunks) == 1
        assert chunks[0]["speaker"] == "default"

    def test_parse_diarization_with_speakers(self):
        from app.services.audiobook.textproc import parse_diarization

        text = "ALICE: Hello there\nBOB: How are you"
        chunks = parse_diarization(text)
        speakers = [c["speaker"] for c in chunks]
        assert "ALICE" in speakers
        assert "BOB" in speakers

    def test_chunk_split_respects_max_chars(self):
        from app.services.audiobook.textproc import chunk_split

        text = "Hello world. " * 50  # ~650 chars
        chunks = chunk_split(text, max_chars=100)
        assert all(len(c) <= 100 for c in chunks)
        assert len(chunks) > 1

    def test_chunk_split_single_sentence(self):
        from app.services.audiobook.textproc import chunk_split

        text = "Short sentence."
        chunks = chunk_split(text, max_chars=500)
        assert len(chunks) == 1
        assert chunks[0] == "Short sentence."


# =========================================================================
# Rewrite — LLM response validation
# =========================================================================


class TestRewrite:
    """Tests for app.services.audiobook.rewrite validation logic."""

    def test_empty_chapter_text_filtered(self):
        """Chapters with empty/whitespace-only text should be excluded."""
        from app.services.audiobook.rewrite import rewrite

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"title": "Test", "chapters": ['
            '{"title": "Ch1", "text": "Real content"},'
            '{"title": "Ch2", "text": ""},'
            '{"title": "Ch3", "text": "   "}'
            "]}"
        )

        with patch("app.services.audiobook.rewrite.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = (
                mock_response
            )
            cfg = {
                "keys": {"openai": "fake"},
                "llm": {"model": "gpt-4", "temperature": 0.3},
            }
            result = rewrite("source text", cfg)
            # Only Ch1 should survive
            assert len(result["chapters"]) == 1
            assert result["chapters"][0]["title"] == "Ch1"

    def test_non_dict_chapters_skipped(self):
        from app.services.audiobook.rewrite import rewrite

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"title": "Test", "chapters": ["not a dict", {"title": "Real", "text": "Content"}]}'
        )

        with patch("app.services.audiobook.rewrite.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = (
                mock_response
            )
            cfg = {
                "keys": {"openai": "fake"},
                "llm": {"model": "gpt-4", "temperature": 0.3},
            }
            result = rewrite("source text", cfg)
            assert len(result["chapters"]) == 1
            assert result["chapters"][0]["title"] == "Real"

    def test_invalid_json_returns_empty_chapters(self):
        from app.services.audiobook.rewrite import rewrite

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json at all"

        with patch("app.services.audiobook.rewrite.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = (
                mock_response
            )
            cfg = {
                "keys": {"openai": "fake"},
                "llm": {"model": "gpt-4", "temperature": 0.3},
            }
            result = rewrite("source text", cfg)
            assert result["title"] == "Untitled Audiobook"
            assert result["chapters"] == []


# =========================================================================
# Stitch — Audio segment normalization
# =========================================================================


class TestStitch:
    """Tests for app.services.audiobook.stitch."""

    def test_build_chapter_empty_chunks(self):
        from app.services.audiobook.stitch import build_chapter

        cfg = {
            "tts": {"format": "mp3"},
            "audio": {"silence_ms_between_chunks": 220},
        }
        result = build_chapter([], cfg)
        assert len(result) == 0  # empty AudioSegment

    def test_export_book_empty_chapters(self, tmp_path):
        from app.services.audiobook.stitch import export_book

        cfg = {
            "tts": {"format": "mp3"},
            "audio": {
                "silence_ms_between_chapters": 700,
                "target_dbfs": -20.0,
            },
        }
        out = tmp_path / "book.mp3"
        result = export_book([], cfg, out)
        assert result.exists()

    def test_coerce_normalizes_params(self):
        """_coerce should bring a segment in line with the reference."""
        from pydub import AudioSegment

        from app.services.audiobook.stitch import _coerce

        ref = AudioSegment.silent(100, frame_rate=44100)
        ref = ref.set_channels(2).set_sample_width(2)

        seg = AudioSegment.silent(100, frame_rate=22050)
        seg = seg.set_channels(1).set_sample_width(1)

        coerced = _coerce(seg, ref)
        assert coerced.frame_rate == 44100
        assert coerced.channels == 2
        assert coerced.sample_width == 2

    def test_export_book_skips_empty_first_chapter(self, tmp_path):
        """When the first chapter is empty, export_book should use the first
        non-empty chapter as the reference for audio params."""
        from pydub import AudioSegment

        from app.services.audiobook.stitch import export_book

        empty = AudioSegment.empty()
        real = AudioSegment.silent(500, frame_rate=44100)
        real = real.set_channels(2).set_sample_width(2)

        cfg = {
            "tts": {"format": "mp3"},
            "audio": {
                "silence_ms_between_chapters": 700,
                "target_dbfs": -20.0,
            },
        }
        out = tmp_path / "book.mp3"
        result = export_book([empty, real], cfg, out)
        assert result.exists()


# =========================================================================
# Pipeline — cache key determinism & diarize skip-LLM
# =========================================================================


class TestPipeline:
    """Tests for app.services.audiobook.pipeline helpers."""

    def test_cache_key_deterministic(self):
        from app.services.audiobook.pipeline import _cache_key

        k1 = _cache_key("deepgram", "aura", "mp3", "hello", "abc", 1.0, "")
        k2 = _cache_key("deepgram", "aura", "mp3", "hello", "abc", 1.0, "")
        assert k1 == k2
        assert len(k1) == 24

    def test_cache_key_changes_with_text(self):
        from app.services.audiobook.pipeline import _cache_key

        k1 = _cache_key("deepgram", "aura", "mp3", "hello", "", 1.0, "")
        k2 = _cache_key("deepgram", "aura", "mp3", "world", "", 1.0, "")
        assert k1 != k2

    def test_cache_key_changes_with_lexicon(self):
        from app.services.audiobook.pipeline import _cache_key

        k1 = _cache_key("deepgram", "aura", "mp3", "hello", "lex1", 1.0, "")
        k2 = _cache_key("deepgram", "aura", "mp3", "hello", "lex2", 1.0, "")
        assert k1 != k2


# =========================================================================
# Curator — slugify and safe path helpers
# =========================================================================


class TestCurator:
    """Tests for app.services.audiobook.curator helpers."""

    def test_slugify_normal(self):
        from app.services.audiobook.curator import _slugify

        assert _slugify("Hello World!") == "hello-world"

    def test_slugify_empty_returns_untitled(self):
        from app.services.audiobook.curator import _slugify

        assert _slugify("") == "untitled"
        assert _slugify("!!!") == "untitled"

    def test_slugify_unicode(self):
        from app.services.audiobook.curator import _slugify

        result = _slugify("Bitcoin — A New Hope")
        assert result  # Should produce something non-empty
        assert " " not in result
