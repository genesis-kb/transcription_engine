import pytest
from unittest.mock import MagicMock
from app.services.factory import get_asr_service, get_available_providers

def test_get_asr_service_unknown_provider():
    mock_writer = MagicMock()
    with pytest.raises(ValueError) as excinfo:
        get_asr_service("does-not-exist", {}, mock_writer)
    
    available = get_available_providers()
    error_msg = str(excinfo.value)
    
    assert "Unknown ASR provider: 'does-not-exist'" in error_msg
    # Check that the available providers are listed in the error message
    # e.g., "Choose from ['deepgram', 'smallestai', 'whisper']"
    for p in available:
        assert p in error_msg
