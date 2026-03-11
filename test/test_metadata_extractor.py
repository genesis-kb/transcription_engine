import pytest
from unittest import mock
from app.services.metadata_extractor import MetadataExtractorService


@pytest.fixture
def mock_transcript():
    """Create a mock transcript with YouTube metadata."""
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
    """Create a mock transcript without YouTube metadata."""
    transcript = mock.MagicMock()
    transcript.source.title = "Local Audio Talk"
    transcript.source.speakers = ["Manual Speaker"]
    transcript.source.conference = None
    transcript.source.topics = []
    transcript.source.youtube_metadata = None
    return transcript


@pytest.fixture
def mock_transcript_with_speakers():
    """Create a mock transcript with manually-set speakers."""
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


class TestMetadataExtractorService:

    @mock.patch("app.services.metadata_extractor.genai")
    @mock.patch("app.services.metadata_extractor.settings")
    def test_process_extracts_metadata(self, mock_settings, mock_genai, mock_transcript):
        """Test that process() correctly extracts and sets metadata."""
        mock_settings.GOOGLE_API_KEY = "test-key"

        # Mock the Gemini model response
        mock_model_instance = mock.MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model_instance
        mock_model_instance.generate_content.return_value.text = (
            '{"speakers": ["Pieter Wuille"], "conference": "Bitcoin 2021", '
            '"topics": ["Taproot", "Schnorr Signatures", "Script Upgrades"]}'
        )

        service = MetadataExtractorService()
        service.process(mock_transcript)

        assert mock_transcript.source.speakers == ["Pieter Wuille"]
        assert mock_transcript.source.conference == "Bitcoin 2021"
        assert mock_transcript.source.topics == ["Taproot", "Schnorr Signatures", "Script Upgrades"]

    @mock.patch("app.services.metadata_extractor.genai")
    @mock.patch("app.services.metadata_extractor.settings")
    def test_process_skips_no_youtube(self, mock_settings, mock_genai, mock_transcript_no_youtube):
        """Test that process() skips when no YouTube metadata is present."""
        mock_settings.GOOGLE_API_KEY = "test-key"

        service = MetadataExtractorService()
        service.process(mock_transcript_no_youtube)

        # Should not call the LLM at all
        mock_genai.GenerativeModel.assert_not_called()
        # Speakers should remain as manually set
        assert mock_transcript_no_youtube.source.speakers == ["Manual Speaker"]

    @mock.patch("app.services.metadata_extractor.genai")
    @mock.patch("app.services.metadata_extractor.settings")
    def test_process_preserves_manual_speakers(self, mock_settings, mock_genai, mock_transcript_with_speakers):
        """Test that manually-set speakers are NOT overwritten."""
        mock_settings.GOOGLE_API_KEY = "test-key"

        mock_model_instance = mock.MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model_instance
        mock_model_instance.generate_content.return_value.text = (
            '{"speakers": ["LLM Extracted Speaker"], "conference": "Some Event", "topics": ["Mining"]}'
        )

        service = MetadataExtractorService()
        service.process(mock_transcript_with_speakers)

        # Speakers should NOT be overwritten
        assert mock_transcript_with_speakers.source.speakers == ["Already Set Speaker"]
        # But conference and topics should still be set
        assert mock_transcript_with_speakers.source.conference == "Some Event"
        assert mock_transcript_with_speakers.source.topics == ["Mining"]

    @mock.patch("app.services.metadata_extractor.genai")
    @mock.patch("app.services.metadata_extractor.settings")
    def test_process_handles_llm_failure(self, mock_settings, mock_genai, mock_transcript):
        """Test that LLM failure leaves existing metadata intact."""
        mock_settings.GOOGLE_API_KEY = "test-key"

        mock_model_instance = mock.MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model_instance
        mock_model_instance.generate_content.side_effect = Exception("API Error")

        service = MetadataExtractorService()
        service.process(mock_transcript)

        # Should leave metadata unchanged
        assert mock_transcript.source.speakers == []
        assert mock_transcript.source.conference is None
        assert mock_transcript.source.topics == []

    @mock.patch("app.services.metadata_extractor.genai")
    @mock.patch("app.services.metadata_extractor.settings")
    def test_process_handles_malformed_json(self, mock_settings, mock_genai, mock_transcript):
        """Test graceful handling of malformed LLM JSON response."""
        mock_settings.GOOGLE_API_KEY = "test-key"

        mock_model_instance = mock.MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model_instance
        mock_model_instance.generate_content.return_value.text = "not valid json {{"

        service = MetadataExtractorService()
        service.process(mock_transcript)

        # Should leave metadata unchanged on parse failure
        assert mock_transcript.source.speakers == []
        assert mock_transcript.source.conference is None
        assert mock_transcript.source.topics == []

    def test_parse_response_valid_json(self):
        """Test _parse_response with valid JSON."""
        service = MetadataExtractorService.__new__(MetadataExtractorService)
        result = service._parse_response(
            '{"speakers": ["Alice", "Bob"], "conference": "BTC Conf", "topics": ["Mining"]}'
        )
        assert result == {
            'speakers': ['Alice', 'Bob'],
            'conference': 'BTC Conf',
            'topics': ['Mining']
        }

    def test_parse_response_markdown_wrapped(self):
        """Test _parse_response with markdown code-block wrapped JSON."""
        service = MetadataExtractorService.__new__(MetadataExtractorService)
        result = service._parse_response(
            '```json\n{"speakers": ["Alice"], "conference": "Event", "topics": ["Taproot"]}\n```'
        )
        assert result == {
            'speakers': ['Alice'],
            'conference': 'Event',
            'topics': ['Taproot']
        }

    def test_parse_response_invalid_json(self):
        """Test _parse_response with invalid JSON returns empty defaults."""
        service = MetadataExtractorService.__new__(MetadataExtractorService)
        result = service._parse_response("this is not json")
        assert result == {'speakers': [], 'conference': '', 'topics': []}

    def test_build_prompt_includes_metadata(self):
        """Test that the prompt includes all provided metadata."""
        service = MetadataExtractorService.__new__(MetadataExtractorService)
        prompt = service._build_prompt(
            title="Test Talk",
            description="A description",
            channel_name="Test Channel",
            tags=["bitcoin", "mining"]
        )
        assert "Test Talk" in prompt
        assert "Test Channel" in prompt
        assert "bitcoin, mining" in prompt
        assert "A description" in prompt
