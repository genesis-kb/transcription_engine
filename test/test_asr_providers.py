"""
Section 2 — ASR Provider Tests
================================
Autodiscovery: ``get_available_providers()`` scans ``app/services/providers/``
at import time and returns every registered provider name.  All parametrised
tests below automatically cover new providers the moment a new
``BaseTranscriptionService`` subclass is added to that package.

Notes:
- VibeVoice is excluded from CI if it is not present in the registry
  (it will appear automatically once integrated).
- Providers that require real API keys are skipped when the key is absent.
"""

import pytest
from unittest.mock import MagicMock

from app.services.factory import get_available_providers, get_asr_service
from app.services.providers.base import BaseTranscriptionService

pytestmark = [pytest.mark.unit, pytest.mark.services]

# ---------------------------------------------------------------------------
# Per-provider metadata: env var required, and whether to skip in CI
# ---------------------------------------------------------------------------
PROVIDER_ENV_KEYS: dict[str, str] = {
    "deepgram":  "DEEPGRAM_API_KEY",
    "smallestai": "SMALLEST_API_KEY",
}

# Providers that require heavy local resources — skip unless explicitly opted in.
RESOURCE_INTENSIVE = {"vibevoice"}


def _inject_provider_env(provider: str, monkeypatch) -> None:
    """Inject a dummy API key for providers that require one."""
    env_key = PROVIDER_ENV_KEYS.get(provider)
    if env_key:
        monkeypatch.setenv(env_key, f"dummy-{provider}-key")


# ---------------------------------------------------------------------------
# Parametrised: every discovered provider must instantiate successfully
# ---------------------------------------------------------------------------

@pytest.fixture(params=get_available_providers())
def provider_name(request):
    """One test execution per discovered ASR provider."""
    return request.param


def test_provider_instantiation(provider_name, mock_data_writer, monkeypatch):
    """Every discovered provider must return a valid BaseTranscriptionService."""
    if provider_name in RESOURCE_INTENSIVE:
        pytest.skip(f"'{provider_name}' skipped in CI — requires 16 GB+ RAM")

    _inject_provider_env(provider_name, monkeypatch)

    service = get_asr_service(provider_name, {}, mock_data_writer)

    assert isinstance(service, BaseTranscriptionService), (
        f"get_asr_service('{provider_name}') did not return a BaseTranscriptionService"
    )
    assert service.__class__.PROVIDER_NAME == provider_name, (
        f"PROVIDER_NAME mismatch: expected '{provider_name}', "
        f"got '{service.__class__.PROVIDER_NAME}'"
    )


def test_provider_from_config_passes_kwargs(mock_data_writer, monkeypatch):
    """
    WhisperService.from_config must honour the 'model' key passed via config dict.
    This exercises the from_config() contract shared by all providers.
    """
    svc = get_asr_service("whisper", {"model": "small"}, mock_data_writer)
    assert svc.model == "small"


def test_all_providers_have_non_empty_provider_name(mock_data_writer, monkeypatch):
    """PROVIDER_NAME must be a non-empty string for every registered provider."""
    for name in get_available_providers():
        if name in RESOURCE_INTENSIVE:
            continue
        _inject_provider_env(name, monkeypatch)
        svc = get_asr_service(name, {}, mock_data_writer)
        assert isinstance(svc.__class__.PROVIDER_NAME, str)
        assert svc.__class__.PROVIDER_NAME.strip() != ""


# ---------------------------------------------------------------------------
# Invalid provider — error message must list all known providers
# ---------------------------------------------------------------------------

def test_invalid_provider_raises_value_error(mock_data_writer):
    """Requesting an unknown provider must raise ValueError."""
    with pytest.raises(ValueError):
        get_asr_service("not_a_real_provider", {}, mock_data_writer)


def test_invalid_provider_error_lists_all_available(mock_data_writer):
    """The ValueError message must mention every currently registered provider."""
    available = get_available_providers()
    with pytest.raises(ValueError) as exc_info:
        get_asr_service("not_a_real_provider", {}, mock_data_writer)

    err = str(exc_info.value)
    assert "Unknown ASR provider: 'not_a_real_provider'" in err
    for provider in available:
        assert provider in err, (
            f"Provider '{provider}' missing from error message: {err!r}"
        )


# ---------------------------------------------------------------------------
# Registry state
# ---------------------------------------------------------------------------

def test_registry_has_at_least_one_provider():
    """The registry must contain at least one provider after discovery."""
    providers = get_available_providers()
    assert len(providers) >= 1, "No ASR providers discovered — check app/services/providers/"


def test_no_duplicate_provider_names():
    """Each provider name must appear exactly once in the registry."""
    providers = get_available_providers()
    assert len(providers) == len(set(providers)), (
        f"Duplicate provider names detected: {providers}"
    )
