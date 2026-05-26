"""Tests for the Sliding Context Window (CoS2W) implementation in CorrectionService."""

import pytest

from app.services.correction import CorrectionService, CONTEXT_WINDOW_CHARS


class TestSnapToWordBoundary:
    """Tests for _snap_to_word_boundary — ensures context windows never cut words."""

    def test_short_text_returns_as_is(self):
        """If text is shorter than max_chars, return it unchanged."""
        result = CorrectionService._snap_to_word_boundary("hello world", 500, snap_end=True)
        assert result == "hello world"

    def test_snap_end_trims_partial_word_at_start(self):
        """When taking the tail of text, the first partial word should be dropped."""
        # Simulate a 600-char text where the last 500 chars start mid-word
        text = "x" * 100 + " Bitcoin is a decentralized currency" + " word" * 93
        result = CorrectionService._snap_to_word_boundary(text, 500, snap_end=True)
        # The result should not start with a partial word
        assert not result[0].isalpha() or result == result.lstrip()
        # And should be shorter than or equal to 500 chars
        assert len(result) <= 500

    def test_snap_start_trims_partial_word_at_end(self):
        """When taking the head of text, the last partial word should be dropped."""
        text = "Bitcoin is a decentralized digital currency" + " word" * 120
        result = CorrectionService._snap_to_word_boundary(text, 500, snap_end=False)
        # The result should not end with a partial word
        assert len(result) <= 500
        # Last char should be a letter (complete word) not a space
        assert result[-1].isalpha()

    def test_snap_end_handles_newlines(self):
        """Newlines should be treated as word boundaries, not just spaces."""
        text = "A" * 300 + "\nBitcoin is great " + "B" * 200
        result = CorrectionService._snap_to_word_boundary(text, 500, snap_end=True)
        # Should not start with a partial word
        assert "\n" not in result[:5] or result[0] != "A"

    def test_snap_start_handles_tabs(self):
        """Tabs should be treated as word boundaries."""
        text = "word1\tword2 word3 " + "x" * 600
        result = CorrectionService._snap_to_word_boundary(text, 20, snap_end=False)
        assert len(result) <= 20

    def test_no_whitespace_returns_raw_slice(self):
        """If the slice has no whitespace at all, return the raw slice."""
        text = "A" * 1000
        result = CorrectionService._snap_to_word_boundary(text, 500, snap_end=True)
        assert len(result) == 500

    def test_exact_boundary(self):
        """Text exactly at max_chars should be returned as-is."""
        text = "hello world this is"
        result = CorrectionService._snap_to_word_boundary(text, len(text), snap_end=True)
        assert result == text


class TestCoS2WContextInjection:
    """Tests for the process() loop's context extraction logic."""

    def test_single_chunk_no_context(self):
        """A single chunk should have no pre_context or lookahead."""
        service = CorrectionService.__new__(CorrectionService)
        chunks = ["This is a single chunk of text."]
        num_chunks = len(chunks)

        for i, chunk in enumerate(chunks, 1):
            pre_context = ""
            lookahead = ""
            if i > 1:
                pre_context = service._snap_to_word_boundary(
                    chunks[i-2], CONTEXT_WINDOW_CHARS, snap_end=True
                )
            if i < num_chunks:
                lookahead = service._snap_to_word_boundary(
                    chunks[i], CONTEXT_WINDOW_CHARS, snap_end=False
                )
            assert pre_context == ""
            assert lookahead == ""

    def test_two_chunks_context(self):
        """With 2 chunks, chunk 1 gets lookahead, chunk 2 gets pre_context."""
        service = CorrectionService.__new__(CorrectionService)
        chunks = ["First chunk content here.", "Second chunk content here."]
        num_chunks = len(chunks)

        results = []
        for i, chunk in enumerate(chunks, 1):
            pre_context = ""
            lookahead = ""
            if i > 1:
                pre_context = service._snap_to_word_boundary(
                    chunks[i-2], CONTEXT_WINDOW_CHARS, snap_end=True
                )
            if i < num_chunks:
                lookahead = service._snap_to_word_boundary(
                    chunks[i], CONTEXT_WINDOW_CHARS, snap_end=False
                )
            results.append((pre_context, lookahead))

        # Chunk 1: no pre_context, has lookahead
        assert results[0][0] == ""
        assert "Second" in results[0][1]

        # Chunk 2: has pre_context, no lookahead
        assert "First" in results[1][0]
        assert results[1][1] == ""

    def test_three_chunks_middle_has_both(self):
        """The middle chunk in a 3-chunk split should have both pre_context and lookahead."""
        service = CorrectionService.__new__(CorrectionService)
        chunks = ["First chunk.", "Middle chunk.", "Last chunk."]
        num_chunks = len(chunks)

        i = 2  # Middle chunk (1-indexed)
        pre_context = ""
        lookahead = ""
        if i > 1:
            pre_context = service._snap_to_word_boundary(
                chunks[i-2], CONTEXT_WINDOW_CHARS, snap_end=True
            )
        if i < num_chunks:
            lookahead = service._snap_to_word_boundary(
                chunks[i], CONTEXT_WINDOW_CHARS, snap_end=False
            )

        assert "First" in pre_context
        assert "Last" in lookahead


class TestPromptContextOrdering:
    """Ensure the LLM prompt has correct temporal ordering: pre → focus → lookahead."""

    def test_prompt_temporal_ordering(self):
        """Pre-Context should appear before Transcript Start, Lookahead after Transcript End."""
        service = CorrectionService.__new__(CorrectionService)
        service.tag_manager = None  # Not needed for prompt building

        prompt = service._build_enhanced_prompt(
            text="This is the focus chunk.",
            keywords=[],
            metadata={},
            global_context={},
            pre_context="Previous segment ending here.",
            lookahead="Next segment starting here.",
        )

        pre_idx = prompt.index("Pre-Context")
        start_idx = prompt.index("Transcript Start")
        end_idx = prompt.index("Transcript End")
        look_idx = prompt.index("Lookahead")

        # Temporal order must be: Pre-Context → Transcript Start → Transcript End → Lookahead
        assert pre_idx < start_idx < end_idx < look_idx

    def test_prompt_no_context_when_empty(self):
        """No context sections should appear when pre_context and lookahead are empty."""
        service = CorrectionService.__new__(CorrectionService)
        service.tag_manager = None

        prompt = service._build_enhanced_prompt(
            text="This is the focus chunk.",
            keywords=[],
            metadata={},
            global_context={},
            pre_context="",
            lookahead="",
        )

        assert "Pre-Context" not in prompt
        assert "Lookahead" not in prompt
        assert "Transcript Start" in prompt
