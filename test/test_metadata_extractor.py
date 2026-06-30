"""
MetadataExtractorService Unit Tests
=====================================
Covers:
- ``process()`` with YouTube metadata  → LLM called, fields set
- ``process()`` with no YouTube metadata → LLM NOT called
- ``process()`` preserves manually-set speakers
- ``process()`` handles LLM failure gracefully
- ``process()`` handles malformed JSON from LLM
- ``_parse_response()`` — valid JSON, markdown-wrapped JSON, invalid JSON
- ``_build_prompt()``  — verifies key fields appear in the generated prompt

Ported verbatim from ``test/test_metadata_extractor.py``.
"""

from unittest import mock

import pytest

from app.services.metadata_extractor import MetadataExtractorService

pytestmark = [pytest.mark.unit, pytest.mark.services]


# ---------------------------------------------------------------------------
# Local fixtures (specific to this module)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_transcript_with_youtube():
    """Mock transcript that has YouTube metadata."""
    transcript = mock.MagicMock()
    transcript.source.title = "Taproot Activation - Pieter Wuille - Bitcoin 2021"
    transcript.source.speakers = []
    transcript.source.conference = None
    transcript.source.topics = []
    transcript.source.youtube_metadata = {
        "description": "Pieter Wuille discusses the Taproot upgrade and its implications.",
        "tags": ["bitcoin", "taproot", "segwit", "schnorr"],
        "categories": ["Science & Technology"],
        "channel_name": "Bitcoin Magazine",
    }
    return transcript


@pytest.fixture
def mock_transcript_no_youtube():
    """Mock transcript without YouTube metadata."""
    transcript = mock.MagicMock()
    transcript.source.title = "Local Audio Talk"
    transcript.source.speakers = ["Manual Speaker"]
    transcript.source.conference = None
    transcript.source.topics = []
    transcript.source.youtube_metadata = None
    return transcript


@pytest.fixture
def mock_transcript_with_speakers():
    """Mock transcript with already-set speakers (should not be overwritten)."""
    transcript = mock.MagicMock()
    transcript.source.title = "Some Talk"
    transcript.source.speakers = ["Already Set Speaker"]
    transcript.source.conference = None
    transcript.source.topics = []
    transcript.source.youtube_metadata = {
        "description": "A talk.",
        "tags": ["bitcoin"],
        "categories": ["Education"],
        "channel_name": "Test Channel",
    }
    return transcript


def _mock_genai_client(response_text: str):
    """Return a mock genai.Client that yields the given text."""
    client = mock.MagicMock()
    client.models.generate_content.return_value.text = response_text
    return client


# ---------------------------------------------------------------------------
# process() tests
# ---------------------------------------------------------------------------

class TestMetadataExtractorServiceProcess:

    @mock.patch("app.services.metadata_extractor.genai")
    @mock.patch("app.services.metadata_extractor.settings")
    def test_process_extracts_metadata(
        self, mock_settings, mock_genai, mock_transcript_with_youtube
    ):
        """process() must extract speakers, conference, and topics from YouTube metadata."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_genai.Client.return_value = _mock_genai_client(
            '{"speakers": ["Pieter Wuille"], "conference": "Bitcoin 2021", '
            '"topics": ["Taproot", "Schnorr Signatures", "Script Upgrades"]}'
        )

        MetadataExtractorService().process(mock_transcript_with_youtube)

        assert mock_transcript_with_youtube.source.speakers == ["Pieter Wuille"]
        assert mock_transcript_with_youtube.source.conference == "Bitcoin 2021"
        assert mock_transcript_with_youtube.source.topics == [
            "Taproot", "Schnorr Signatures", "Script Upgrades"
        ]

    @mock.patch("app.services.metadata_extractor.genai")
    @mock.patch("app.services.metadata_extractor.settings")
    def test_process_skips_when_no_youtube_metadata(
        self, mock_settings, mock_genai, mock_transcript_no_youtube
    ):
        """process() must NOT call the LLM when youtube_metadata is None."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_client = mock.MagicMock()
        mock_genai.Client.return_value = mock_client

        MetadataExtractorService().process(mock_transcript_no_youtube)

        mock_client.models.generate_content.assert_not_called()
        assert mock_transcript_no_youtube.source.speakers == ["Manual Speaker"]

    @mock.patch("app.services.metadata_extractor.genai")
    @mock.patch("app.services.metadata_extractor.settings")
    def test_process_preserves_manual_speakers(
        self, mock_settings, mock_genai, mock_transcript_with_speakers
    ):
        """Manually-set speakers must NOT be overwritten by LLM extraction."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_genai.Client.return_value = _mock_genai_client(
            '{"speakers": ["LLM Extracted Speaker"], "conference": "Some Event", "topics": ["Mining"]}'
        )

        MetadataExtractorService().process(mock_transcript_with_speakers)

        assert mock_transcript_with_speakers.source.speakers == ["Already Set Speaker"]
        assert mock_transcript_with_speakers.source.conference == "Some Event"
        assert mock_transcript_with_speakers.source.topics == ["Mining"]

    @mock.patch("app.services.metadata_extractor.genai")
    @mock.patch("app.services.metadata_extractor.settings")
    def test_process_handles_llm_failure(
        self, mock_settings, mock_genai, mock_transcript_with_youtube
    ):
        """An exception from the LLM must leave existing metadata intact."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_client = mock.MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API Error")
        mock_genai.Client.return_value = mock_client

        MetadataExtractorService().process(mock_transcript_with_youtube)

        assert mock_transcript_with_youtube.source.speakers == []
        assert mock_transcript_with_youtube.source.conference is None
        assert mock_transcript_with_youtube.source.topics == []

    @mock.patch("app.services.metadata_extractor.genai")
    @mock.patch("app.services.metadata_extractor.settings")
    def test_process_handles_malformed_json(
        self, mock_settings, mock_genai, mock_transcript_with_youtube
    ):
        """Malformed JSON from the LLM must not crash; metadata stays unchanged."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_genai.Client.return_value = _mock_genai_client("not valid json {{")

        MetadataExtractorService().process(mock_transcript_with_youtube)

        assert mock_transcript_with_youtube.source.speakers == []
        assert mock_transcript_with_youtube.source.conference is None
        assert mock_transcript_with_youtube.source.topics == []


# ---------------------------------------------------------------------------
# _parse_response() tests
# ---------------------------------------------------------------------------

class TestMetadataExtractorParseResponse:
    """Unit tests for the internal _parse_response helper."""

    # Use __new__ to bypass __init__ (avoids needing a real API key)
    @pytest.fixture
    def svc(self):
        return MetadataExtractorService.__new__(MetadataExtractorService)

    def test_valid_json(self, svc):
        result = svc._parse_response(
            '{"speakers": ["Alice", "Bob"], "conference": "BTC Conf", "topics": ["Mining"]}'
        )
        assert result == {
            "speakers": ["Alice", "Bob"],
            "conference": "BTC Conf",
            "topics": ["Mining"],
        }

    def test_markdown_wrapped_json(self, svc):
        result = svc._parse_response(
            '```json\n{"speakers": ["Alice"], "conference": "Event", "topics": ["Taproot"]}\n```'
        )
        assert result == {
            "speakers": ["Alice"],
            "conference": "Event",
            "topics": ["Taproot"],
        }

    def test_invalid_json_returns_defaults(self, svc):
        result = svc._parse_response("this is not json")
        assert result == {"speakers": [], "conference": "", "topics": []}


# ---------------------------------------------------------------------------
# _build_prompt() tests
# ---------------------------------------------------------------------------

class TestMetadataExtractorBuildPrompt:
    """Unit tests for the internal _build_prompt helper."""

    @pytest.fixture
    def svc(self):
        return MetadataExtractorService.__new__(MetadataExtractorService)

    def test_prompt_includes_all_metadata(self, svc):
        prompt = svc._build_prompt(
            title="Test Talk",
            description="A description",
            channel_name="Test Channel",
            tags=["bitcoin", "mining"],
        )
        assert "Test Talk" in prompt
        assert "Test Channel" in prompt
        assert "bitcoin, mining" in prompt
        assert "A description" in prompt
