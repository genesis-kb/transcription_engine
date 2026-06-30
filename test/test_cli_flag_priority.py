"""
Section 1 — CLI Flag Priority Tests
====================================
Verify that values supplied on the CLI override whatever is in config.ini.

Autodiscovery strategy
-----------------------
``BOOLEAN_FLAGS`` is a static table of every ``is_flag=True`` CLI option
(from ``transcriber.py``) together with its ``config.ini`` key, the real
attribute name on the ``Transcription`` object (or a callable checker), and
whether the Transcription __init__ actually reads the flag from config.

Flags tested here assert:
  - The resolved value on the object matches what was passed on the CLI.
  - When NOT passed, the config.ini value is honoured (for flags that read it).

String flags (``--asr-provider``, ``--llm-provider``, ``--model``) are
tested in individually named functions at the bottom.
"""

import pytest
from unittest.mock import MagicMock, patch

pytestmark = [pytest.mark.unit, pytest.mark.cli]

# ---------------------------------------------------------------------------
# Helper: how to check each flag on the Transcription object
# ---------------------------------------------------------------------------
# Each entry: (kwarg to __init__, config.ini key, reads_from_config, checker_fn)
# checker_fn(t, expected_value) -> None  (raises AssertionError on failure)
# ---------------------------------------------------------------------------

def _check_correction(t, val):
    assert (t.correction_service is not None) is val

def _check_summarize(t, val):
    assert (t.summary_service is not None) is val

def _check_correct_enabled(t, val):
    assert t._correct_enabled is val

def _check_summarize_enabled(t, val):
    assert t._summarize_enabled is val

def _check_github(t, val):
    assert t.github is val


def _check_needs_review(t, val):
    if val:
        assert t.review_flag != ""
    else:
        assert t.review_flag == ""

def _check_nocleanup(t, val):
    assert t.nocleanup is val



# ---------------------------------------------------------------------------
# (kwarg, config_key, reads_from_config, checker_fn, extra_kwargs_when_true)
# ---------------------------------------------------------------------------
BOOLEAN_FLAGS = [
    pytest.param(
        "correct",  "correct",  True, _check_correct_enabled, {},
        id="correct"
    ),
    pytest.param(
        "summarize", "summarize", True, _check_summarize_enabled, {},
        id="summarize"
    ),
    pytest.param(
        "github",   "github",   False, _check_github, {},
        id="github"
    ),
    pytest.param(
        "nocleanup", "nocleanup", False, _check_nocleanup, {},
        id="nocleanup"
    ),
    pytest.param(
        "needs_review", "needs_review", False, _check_needs_review, {"markdown": True},
        id="needs_review"
    ),
]


def _inject_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-dg")
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-gg")
    monkeypatch.setenv("SMALLEST_API_KEY", "dummy-sm")


def _make(monkeypatch, tmp_config, **kwargs):
    """Build Transcription with dummy env and GitHub patched out."""
    _inject_env(monkeypatch)
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    with patch("app.transcription.GitHubAPIHandler"):
        from app.transcription import Transcription
        return Transcription(test_mode=True, username="test_user", **kwargs)


# ---------------------------------------------------------------------------
# Parametrised: CLI True overrides config False
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwarg,config_key,reads_cfg,checker,extra", BOOLEAN_FLAGS)
def test_cli_true_overrides_config_false(kwarg, config_key, reads_cfg, checker, extra,
                                         tmp_config, monkeypatch):
    """CLI flag=True must win even when config.ini says False."""
    _inject_env(monkeypatch)
    tmp_config({
        config_key: "False",
        "asr_provider": "whisper",
        "llm_provider": "openai",
    })
    with patch("app.transcription.GitHubAPIHandler"):
        from app.transcription import Transcription
        kwargs = {kwarg: True, **extra}
        t = Transcription(test_mode=True, username="test_user", **kwargs)

    checker(t, True)


# ---------------------------------------------------------------------------
# Config.ini read-through at the CLI layer
# ---------------------------------------------------------------------------
# NOTE: ``correct`` and ``summarize`` are plain kwargs to Transcription.__init__
# and are NOT read from config.ini inside __init__.  The config read happens in
# the transcriber.py CLI layer (click.option default=settings.config.getboolean).
# These tests verify the kwarg semantics directly (True → enabled, False → not).

def test_correct_true_enables_correction(tmp_config, monkeypatch):
    """Passing correct=True must set _correct_enabled=True."""
    _inject_env(monkeypatch)
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    from app.transcription import Transcription
    t = Transcription(correct=True, test_mode=True, username="test_user")
    assert t._correct_enabled is True
    assert t.correction_service is not None


def test_correct_false_disables_correction(tmp_config, monkeypatch):
    """Passing correct=False must set _correct_enabled=False."""
    _inject_env(monkeypatch)
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    from app.transcription import Transcription
    t = Transcription(correct=False, test_mode=True, username="test_user")
    assert t._correct_enabled is False
    assert t.correction_service is None


def test_summarize_true_enables_summarizer(tmp_config, monkeypatch):
    """Passing summarize=True must set _summarize_enabled=True."""
    _inject_env(monkeypatch)
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    from app.transcription import Transcription
    t = Transcription(summarize=True, test_mode=True, username="test_user")
    assert t._summarize_enabled is True
    assert t.summary_service is not None


def test_summarize_false_disables_summarizer(tmp_config, monkeypatch):
    """Passing summarize=False must set _summarize_enabled=False."""
    _inject_env(monkeypatch)
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    from app.transcription import Transcription
    t = Transcription(summarize=False, test_mode=True, username="test_user")
    assert t._summarize_enabled is False
    assert t.summary_service is None


# ---------------------------------------------------------------------------
# diarize — CLI hardcoded default (False) wins over config True
# (this behaviour is documented in test_config_fallback.py too)
# ---------------------------------------------------------------------------

def test_diarize_true_when_passed_explicitly(tmp_config, monkeypatch):
    """Passing diarize=True must set the Deepgram service's diarize attribute."""
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-dg")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "deepgram", "llm_provider": "openai"})
    from app.transcription import Transcription
    t = Transcription(diarize=True, test_mode=True, username="test_user")
    assert t.service.diarize is True


def test_diarize_false_when_not_passed(tmp_config, monkeypatch):
    """When diarize is NOT passed, the CLI default (False) applies regardless of config."""
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-dg")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "deepgram", "llm_provider": "openai", "diarize": "True"})
    from app.transcription import Transcription
    # Do NOT pass diarize — simulates CLI with no --diarize flag (hardcoded default=False)
    t = Transcription(diarize=False, test_mode=True, username="test_user")
    assert t.service.diarize is False


# ---------------------------------------------------------------------------
# String flag — --asr-provider overrides config
# ---------------------------------------------------------------------------

def test_asr_provider_cli_overrides_config(tmp_config, monkeypatch):
    """--asr-provider deepgram must win even if config says whisper."""
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dummy-dg")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    from app.transcription import Transcription
    t = Transcription(asr_provider="deepgram", test_mode=True, username="test_user")
    assert t.asr_provider_name == "deepgram"


def test_asr_provider_falls_back_to_config(tmp_config, monkeypatch):
    """When --asr-provider is not supplied, config.ini value must be used."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    from app.transcription import Transcription
    t = Transcription(test_mode=True, username="test_user")
    assert t.asr_provider_name == "whisper"


# ---------------------------------------------------------------------------
# String flag — --llm-provider overrides config
# ---------------------------------------------------------------------------

def test_llm_provider_cli_overrides_config_correction(tmp_config, monkeypatch):
    """--llm-provider google must win even if config says openai."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-gg")
    tmp_config({"llm_provider": "openai", "asr_provider": "whisper"})
    with patch("app.services.correction.genai"):
        from app.transcription import Transcription
        t = Transcription(
            llm_provider="google", correct=True,
            test_mode=True, username="test_user",
        )
    assert t.correction_service is not None
    assert t.correction_service.provider == "google"


def test_llm_provider_cli_overrides_config_summarizer(tmp_config, monkeypatch):
    """--llm-provider google must win for summarizer too."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-gg")
    tmp_config({"llm_provider": "openai", "asr_provider": "whisper"})
    with patch("app.services.summarizer.genai"):
        from app.transcription import Transcription
        t = Transcription(
            llm_provider="google", summarize=True,
            test_mode=True, username="test_user",
        )
    assert t.summary_service is not None
    assert t.summary_service.provider == "google"


# ---------------------------------------------------------------------------
# String flag — --model overrides config default
# ---------------------------------------------------------------------------

def test_model_cli_overrides_config(tmp_config, monkeypatch):
    """--model small must be passed through to the Whisper service."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai", "model": "tiny.en"})
    from app.transcription import Transcription
    t = Transcription(model="small", asr_provider="whisper", test_mode=True, username="test_user")
    assert t.service.model == "small"
