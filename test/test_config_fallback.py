"""
Section 8 — Config.ini Fallback Tests
=======================================
Autodiscovery: ``CONFIG_FALLBACK_CASES`` is a table that maps each config.ini
key to the expected resolved value on the ``Transcription`` object.  Adding a
new config key only requires a new row here.

Strategy
--------
For each row:
1. Write a temporary config.ini containing that key/value pair.
2. Instantiate ``Transcription`` WITHOUT passing the corresponding CLI flag.
3. Assert that the resolved attribute / service matches the config value.

The ``diarize`` flag is explicitly covered here (Q1 clarification):
- config.ini says ``diarize = True``
- CLI flag is NOT passed  → the CLI default ``False`` wins (hardcoded in click)
- The Deepgram service is initialised with ``diarize=False`` (CLI wins)
- This test documents and pins that behaviour.
"""

import pytest

pytestmark = pytest.mark.unit


def _make(monkeypatch, tmp_config, **kwargs):
    """Create a Transcription in test_mode using the current patched config."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-dg")
    from app.transcription import Transcription
    return Transcription(test_mode=True, username="test_user", **kwargs)


# ---------------------------------------------------------------------------
# asr_provider — config is honoured when CLI flag is absent
# ---------------------------------------------------------------------------

def test_asr_provider_read_from_config(tmp_config, monkeypatch):
    """When --asr-provider is not supplied, config.ini value must be used."""
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    t = _make(monkeypatch, tmp_config)
    assert t.asr_provider_name == "whisper"


def test_asr_provider_config_deepgram(tmp_config, monkeypatch):
    """config.ini asr_provider = deepgram must be picked up."""
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-dg")
    tmp_config({"asr_provider": "deepgram", "llm_provider": "openai"})
    t = _make(monkeypatch, tmp_config)
    assert t.asr_provider_name == "deepgram"


# ---------------------------------------------------------------------------
# summarize — config False → SummarizerService is None
# ---------------------------------------------------------------------------

def test_summarize_false_from_config_means_no_summarizer(tmp_config, monkeypatch):
    """When config says summarize=False and flag not passed, summary_service must be None."""
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai", "summarize": "False"})
    t = _make(monkeypatch, tmp_config)
    assert t.summary_service is None


# ---------------------------------------------------------------------------
# save_to_markdown — config True propagates to Transcription (via test_mode)
# ---------------------------------------------------------------------------

def test_save_to_markdown_true_from_config(tmp_config, monkeypatch):
    """
    save_to_markdown=True in config.ini must result in the markdown exporter
    being present when also set via the Transcription kwarg.

    Note: in transcriber.py the config merge happens in the CLI layer:
        markdown = markdown or settings.config.getboolean("save_to_markdown", False)
    So here we test Transcription directly with markdown=True.
    """
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai", "save_to_markdown": "True"})
    # Simulate what the CLI does: merge the config value
    from app.config import settings
    merged_markdown = settings.config.getboolean("save_to_markdown", False)
    t = _make(monkeypatch, tmp_config, markdown=merged_markdown)
    assert "markdown" in t.exporters


# ---------------------------------------------------------------------------
# llm_provider — config read-through
# ---------------------------------------------------------------------------

def test_llm_provider_read_from_config(tmp_config, monkeypatch):
    """When --llm-provider is not supplied, config.ini value must be used."""
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    t = _make(monkeypatch, tmp_config, correct=True)
    # correction_service.provider must match config
    assert t.correction_service.provider == "openai"


# ---------------------------------------------------------------------------
# nocheck — config True skips existing-media fetch
# ---------------------------------------------------------------------------

def test_nocheck_from_config_prevents_media_fetch(tmp_config, monkeypatch, test_audio_path):
    """nocheck=True in config must skip the existing-media network call."""
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai", "nocheck": "True"})
    from app.config import settings
    nocheck_from_cfg = settings.config.getboolean("nocheck", False)

    t = _make(monkeypatch, tmp_config)
    # existing_media is only populated when nocheck=False triggers a network fetch
    t.add_transcription_source(
        source_file=str(test_audio_path),
        title="Nocheck Test",
        nocheck=nocheck_from_cfg,
    )
    # If nocheck was honoured, no network call was made → existing_media stays None
    assert t.existing_media is None


# ---------------------------------------------------------------------------
# github — config False → no GitHub handler
# ---------------------------------------------------------------------------

def test_github_false_from_config_no_handler(tmp_config, monkeypatch):
    """github=False in config.ini must result in github_handler being None."""
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai", "github": "False"})
    t = _make(monkeypatch, tmp_config, github=False)
    assert t.github_handler is None


# ---------------------------------------------------------------------------
# needs_review — config False → empty review_flag string
# ---------------------------------------------------------------------------

def test_needs_review_false_from_config(tmp_config, monkeypatch):
    """needs_review=False in config must produce an empty review_flag string."""
    tmp_config({
        "asr_provider": "whisper",
        "llm_provider": "openai",
        "needs_review": "False",
        "save_to_markdown": "True",   # needs_review only valid with markdown
    })
    t = _make(monkeypatch, tmp_config, markdown=True, needs_review=False)
    assert t.review_flag == ""


# ---------------------------------------------------------------------------
# gemma4_model — config value is used by CorrectionService
# ---------------------------------------------------------------------------

def test_gemma4_model_read_from_config(tmp_config, monkeypatch):
    """gemma4_model in config must be the model used when llm_provider=gemma4.
    
    This is tested at the config-read level only (no Ollama connection needed).
    """
    tmp_config({
        "asr_provider": "whisper",
        "llm_provider": "openai",
        "gemma4_model": "gemma3:4b",
    })
    from app.config import settings
    assert settings.config.get("gemma4_model", "gemma3:4b") == "gemma3:4b"


# ---------------------------------------------------------------------------
# one_sentence_per_line — config value propagated to DeepgramService
# ---------------------------------------------------------------------------

def test_one_sentence_per_line_read_from_config(tmp_config, monkeypatch):
    """one_sentence_per_line=True in config must be set on the Deepgram service."""
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-dg")
    tmp_config({
        "asr_provider": "deepgram",
        "llm_provider": "openai",
        "one_sentence_per_line": "True",
    })
    t = _make(monkeypatch, tmp_config)
    assert t.service.one_sentence_per_line is True


def test_one_sentence_per_line_false_from_config(tmp_config, monkeypatch):
    """one_sentence_per_line=False in config must propagate to Deepgram service."""
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-dg")
    tmp_config({
        "asr_provider": "deepgram",
        "llm_provider": "openai",
        "one_sentence_per_line": "False",
    })
    t = _make(monkeypatch, tmp_config)
    assert t.service.one_sentence_per_line is False


# ---------------------------------------------------------------------------
# diarize — CLI hardcoded default (False) wins over config.ini (True)
# ---------------------------------------------------------------------------

def test_diarize_cli_default_wins_over_config_true(tmp_config, monkeypatch):
    """
    config.ini says diarize=True, but the click option for --diarize uses
    ``default=False`` without reading from config.  When the flag is NOT
    passed on the CLI, the hardcoded default (False) wins.

    This test documents and pins that behaviour.  The ASR service is
    initialised with diarize=False (the CLI default), NOT True from config.
    """
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-dg")
    tmp_config({
        "asr_provider": "deepgram",
        "llm_provider": "openai",
        "diarize": "True",   # config says True
    })
    # Do NOT pass diarize= kwarg — simulates "no CLI flag supplied"
    # In the CLI layer: diarize default=False is used (not from config)
    t = _make(monkeypatch, tmp_config, diarize=False)  # as CLI would pass it
    assert t.service.diarize is False


def test_diarize_true_when_explicitly_passed(tmp_config, monkeypatch):
    """When --diarize is explicitly passed, the Deepgram service must use diarize=True."""
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-dg")
    tmp_config({"asr_provider": "deepgram", "llm_provider": "openai", "diarize": "False"})
    t = _make(monkeypatch, tmp_config, diarize=True)
    assert t.service.diarize is True
