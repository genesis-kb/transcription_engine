import pytest
from unittest.mock import MagicMock
from app.services.factory import get_asr_service, get_available_providers, reset_registry
from app.services.providers.base import BaseTranscriptionService

@pytest.fixture(autouse=True)
def clean_registry():
    reset_registry()
    yield
    reset_registry()

def test_get_asr_service_unknown_provider():
    mock_writer = MagicMock()
    with pytest.raises(ValueError) as excinfo:
        get_asr_service("does-not-exist", {}, mock_writer)
    
    available = get_available_providers()
    error_msg = str(excinfo.value)
    
    assert "Unknown ASR provider: 'does-not-exist'" in error_msg
    # Check that the available providers are listed in the error message
    for p in available:
        assert p in error_msg

def test_get_asr_service_success():
    mock_writer = MagicMock()
    # Assuming "whisper" is always available in the standard install
    service = get_asr_service("whisper", {}, mock_writer)
    assert isinstance(service, BaseTranscriptionService)
    assert service.__class__.PROVIDER_NAME == "whisper"
