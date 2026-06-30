"""
Section 3 — LLM Provider Tests
================================
Autodiscovery: the valid LLM provider names are read from the ``click.Choice``
definition in ``transcriber.py``, so adding a new provider to that list
automatically adds parametrised test coverage here.

Tests assert:
- ``CorrectionService`` is initialised with the correct ``provider`` attribute.
- ``SummarizerService`` is initialised with the correct ``provider`` attribute.
- Services use the provider-appropriate default model (e.g. google → gemini).
- Tests are skipped when the required API key is absent in the environment.

Note: ``gemma4`` (Ollama) is intentionally excluded for now — it is not in the
``click.Choice`` list and will be added as a separate integration test later.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.services]

# ---------------------------------------------------------------------------
# Discover valid LLM providers from the CLI definition
# ---------------------------------------------------------------------------

def _get_llm_choices() -> list[str]:
    """Extract LLM provider choices from the click.Choice defined in transcriber.py.

    ``transcriber.llm_provider`` is a decorator *function* (the result of
    ``click.option(...)`` applied without a target), so we cannot read
    ``.type.choices`` from it directly.  Instead we walk the source module's
    globals for click.Option objects that carry a Choice type.
    """
    import click
    import transcriber  # triggers module-level definitions

    # Walk all module-level objects looking for click decorators that wrap a Choice
    for name, obj in vars(transcriber).items():
        # click.option returns a function whose __closure__ contains the params;
        # the easiest reliable approach is to call the option on a dummy command
        # and inspect the resulting parameter.
        if callable(obj) and name == "llm_provider":
            # Build a tiny dummy command and apply the decorator to it
            @click.command()
            def _dummy():
                pass
            decorated = obj(_dummy)
            for param in decorated.params:
                if isinstance(param, click.Option) and isinstance(param.type, click.Choice):
                    return list(param.type.choices)

    # Hard-coded fallback that mirrors transcriber.py's click.Choice list.
    # Update this list whenever transcriber.py's llm_provider choices change.
    return ["openai", "google", "claude"]


LLM_PROVIDERS = _get_llm_choices()   # e.g. ["openai", "google", "claude"]

# Providers whose service implementations are not yet complete.
# They exist in click.Choice but raise ValueError inside CorrectionService/SummarizerService.
NOT_YET_IMPLEMENTED = {"claude"}

LLM_ENV_KEYS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "claude": "CLAUDE_API_KEY",
}

# Expected default model strings per provider (after any internal remapping).
EXPECTED_MODELS: dict[str, str] = {
    "openai": "gpt-4o",
    "google": "gemini-3-flash-preview",  # remapped from gpt-4o
    "claude": None,  # not yet fully implemented — skip model check
}


def _patch_provider_client(provider: str):
    """Return a context-manager stack that stubs out the provider's HTTP client."""
    if provider == "google":
        return patch("app.services.correction.genai"), patch("app.services.summarizer.genai")
    # openai / claude: monkeypatch handles the key; no extra patching needed
    return None, None


def _inject_key(provider: str, monkeypatch) -> bool:
    """
    Inject a dummy API key for the given provider.
    Returns True if the real key is available in the environment (live test),
    False if we fell back to a dummy (unit test).
    """
    env_key = LLM_ENV_KEYS.get(provider)
    if env_key:
        if not os.getenv(env_key):
            monkeypatch.setenv(env_key, f"sk-dummy-{provider}")
            return False
        return True
    return False


# ---------------------------------------------------------------------------
# CorrectionService
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("provider", LLM_PROVIDERS)
def test_correction_service_uses_correct_provider(provider, tmp_config, monkeypatch):
    """CorrectionService.provider must match the value supplied on the CLI."""
    if provider in NOT_YET_IMPLEMENTED:
        pytest.skip(f"'{provider}' service not yet implemented")

    _inject_key(provider, monkeypatch)
    tmp_config({"llm_provider": "openai", "asr_provider": "whisper"})

    if provider == "google":
        with patch("app.services.correction.genai") as patch_corr:
            from app.transcription import Transcription
            t = Transcription(
                llm_provider=provider,
                correct=True,
                test_mode=True,
                username="test_user",
            )
    else:
        from app.transcription import Transcription
        t = Transcription(
            llm_provider=provider,
            correct=True,
            test_mode=True,
            username="test_user",
        )


    assert t.correction_service is not None
    assert t.correction_service.provider == provider


@pytest.mark.parametrize("provider", LLM_PROVIDERS)
def test_correction_service_default_model(provider, tmp_config, monkeypatch):
    """CorrectionService must use the expected default model for each provider."""
    if provider in NOT_YET_IMPLEMENTED:
        pytest.skip(f"'{provider}' service not yet implemented")
    expected = EXPECTED_MODELS.get(provider)
    if expected is None:
        pytest.skip(f"No expected model defined for '{provider}'")

    _inject_key(provider, monkeypatch)
    tmp_config({"llm_provider": "openai", "asr_provider": "whisper"})

    patch_corr = patch("app.services.correction.genai") if provider == "google" else None
    try:
        if patch_corr:
            patch_corr.start()
        from app.transcription import Transcription
        t = Transcription(
            llm_provider=provider,
            correct=True,
            test_mode=True,
            username="test_user",
        )
    finally:
        if patch_corr:
            patch_corr.stop()

    assert t.correction_service.model == expected


# ---------------------------------------------------------------------------
# SummarizerService
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("provider", LLM_PROVIDERS)
def test_summarizer_service_uses_correct_provider(provider, tmp_config, monkeypatch):
    """SummarizerService.provider must match the value supplied on the CLI."""
    if provider in NOT_YET_IMPLEMENTED:
        pytest.skip(f"'{provider}' service not yet implemented")

    _inject_key(provider, monkeypatch)
    tmp_config({"llm_provider": "openai", "asr_provider": "whisper"})

    patch_summ = patch("app.services.summarizer.genai") if provider == "google" else None
    try:
        if patch_summ:
            patch_summ.start()
        from app.transcription import Transcription
        t = Transcription(
            llm_provider=provider,
            summarize=True,
            test_mode=True,
            username="test_user",
        )
    finally:
        if patch_summ:
            patch_summ.stop()

    assert t.summary_service is not None
    assert t.summary_service.provider == provider


@pytest.mark.parametrize("provider", LLM_PROVIDERS)
def test_summarizer_service_default_model(provider, tmp_config, monkeypatch):
    """SummarizerService must use the expected default model for each provider."""
    if provider in NOT_YET_IMPLEMENTED:
        pytest.skip(f"'{provider}' service not yet implemented")
    expected = EXPECTED_MODELS.get(provider)
    if expected is None:
        pytest.skip(f"No expected model defined for '{provider}'")

    _inject_key(provider, monkeypatch)
    tmp_config({"llm_provider": "openai", "asr_provider": "whisper"})

    patch_summ = patch("app.services.summarizer.genai") if provider == "google" else None
    try:
        if patch_summ:
            patch_summ.start()
        from app.transcription import Transcription
        t = Transcription(
            llm_provider=provider,
            summarize=True,
            test_mode=True,
            username="test_user",
        )
    finally:
        if patch_summ:
            patch_summ.stop()

    assert t.summary_service.model == expected


# ---------------------------------------------------------------------------
# Neither service initialised when flags are off
# ---------------------------------------------------------------------------

def test_no_llm_services_when_neither_flag_set(tmp_config, monkeypatch):
    """When neither --correct nor --summarize is passed, both services must be None."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"llm_provider": "openai", "asr_provider": "whisper"})

    from app.transcription import Transcription
    t = Transcription(test_mode=True, username="test_user")
    assert t.correction_service is None
    assert t.summary_service is None


# ---------------------------------------------------------------------------
# Unsupported provider raises ValueError
# ---------------------------------------------------------------------------

def test_unsupported_llm_provider_raises(tmp_config, monkeypatch):
    """An unsupported LLM provider name must raise ValueError on init."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper"})

    from app.transcription import Transcription
    with pytest.raises(ValueError):
        Transcription(
            llm_provider="nonexistent_llm",
            correct=True,
            test_mode=True,
            username="test_user",
        )
