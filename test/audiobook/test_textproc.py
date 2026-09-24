"""Tests for app.services.audiobook.textproc — Groups 1-4."""

import pytest
from app.services.audiobook.textproc import (
    clean_text,
    chunk_split,
    normalize,
    parse_diarization,
)


# ── Group 1: clean_text ──────────────────────────────────────────────

class TestCleanText:
    def test_strips_bracketed_timestamp(self):
        assert clean_text("[00:01] Hello world") == "Hello world"

    def test_strips_timestamp_at_line_start(self):
        result = clean_text("00:01 Hello\nworld")
        assert "00:01" not in result
        assert "Hello" in result

    def test_removes_stage_directions(self):
        assert "laughter" not in clean_text("Good [laughter] morning")

    def test_collapses_multiple_spaces(self):
        assert clean_text("hello   world") == "hello world"

    def test_collapses_excess_newlines(self):
        assert clean_text("a\n\n\n\nb") == "a\n\nb"

    def test_retain_speakers_true(self):
        result = clean_text("Alice: Hello there", retain_speakers=True)
        assert "Alice:" in result

    def test_retain_speakers_false(self):
        result = clean_text("Alice: Hello there", retain_speakers=False)
        assert "Alice:" not in result
        assert "Hello there" in result

    def test_chapter_headers_preserved(self):
        for header in ["Chapter 1: Intro", "Part 2: Deep", "Section A: Setup",
                        "Note: Important", "Question: Why?", "Answer: Because"]:
            assert header in clean_text(header)


# ── Group 2: chunk_split ─────────────────────────────────────────────

class TestChunkSplit:
    def test_short_text_single_chunk(self):
        result = chunk_split("Hello world.", 100)
        assert result == ["Hello world."]

    def test_splits_at_sentence_boundary(self):
        text = "First sentence. Second sentence."
        result = chunk_split(text, 20)
        assert len(result) == 2

    def test_long_sentence_splits_further(self):
        text = "Word, " * 50  # lots of prosody breaks
        result = chunk_split(text.strip(), 30)
        assert len(result) > 1

    def test_single_word_exceeding_max_chars(self):
        word = "a" * 50
        result = chunk_split(word, 10)
        assert all(len(c) <= 10 for c in result)

    def test_zero_max_chars_raises(self):
        with pytest.raises(ValueError):
            chunk_split("text", 0)

    def test_empty_string(self):
        assert chunk_split("", 100) == []

    def test_no_chunk_exceeds_max(self):
        text = "The quick brown fox jumps over the lazy dog. " * 20
        result = chunk_split(text, 50)
        assert all(len(c) <= 50 for c in result)


# ── Group 3: normalize ───────────────────────────────────────────────

class TestNormalize:
    def test_money_expansion(self):
        result = normalize("$1.5B")
        assert "billion" in result
        assert "dollars" in result

    def test_money_with_thousands(self):
        result = normalize("$1,200")
        assert "dollars" in result

    def test_acronym_letter_spaced(self):
        result = normalize("FBI")
        assert "F-B-I" in result

    def test_pronounceable_acronym_preserved(self):
        assert "NASA" in normalize("NASA")

    def test_lexicon_key_preserved(self):
        # BTC is in the lexicon so the acronym expander must not touch it
        result = normalize("BTC")
        assert result == "BTC"


# ── Group 4: parse_diarization ────────────────────────────────────────

class TestParseDiarization:
    def test_no_speaker_tags(self):
        result = parse_diarization("Hello world")
        assert len(result) == 1
        assert result[0]["speaker"] == "default"

    def test_two_speakers(self):
        text = "Alice: Hello\nBob: Hi there"
        result = parse_diarization(text)
        speakers = [c["speaker"] for c in result]
        assert "Alice" in speakers
        assert "Bob" in speakers

    def test_preamble_captured_as_default(self):
        text = "Some preamble.\nAlice: Hello"
        result = parse_diarization(text)
        assert result[0]["speaker"] == "default"
        assert "preamble" in result[0]["text"]

    def test_speaker_name_no_trailing_colon(self):
        text = "Alice: Hello"
        result = parse_diarization(text)
        for chunk in result:
            if chunk["speaker"] != "default":
                assert not chunk["speaker"].endswith(":")
