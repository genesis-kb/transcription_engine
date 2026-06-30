"""
Section 4 — Processing Pipeline Tests
=======================================
Autodiscovery: the four meaningful combinations of ``--correct`` x ``--summarize``
are expressed as a parametrize table.  Each combination asserts:
- The correct services are non-None (enabled) or None (disabled).
- The ``pipeline_state["stages"]`` dict contains precisely the expected keys.

Tests run in test_mode so no real audio / LLM calls are made.
"""

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# (correct, summarize, expect_correction_svc, expect_summary_svc)
# ---------------------------------------------------------------------------
PIPELINE_COMBOS = [
    pytest.param(False, False, False, False, id="no_llm"),
    pytest.param(True,  False, True,  False, id="correct_only"),
    pytest.param(False, True,  False, True,  id="summarize_only"),
    pytest.param(True,  True,  True,  True,  id="correct_and_summarize"),
]

EXPECTED_STAGE_NAMES = {
    "media_processing",
    "transcription",
    "metadata_extraction",
    "correction",
    "summarization",
    "export",
}


def _make_transcription(correct, summarize, monkeypatch, tmp_config):
    """Build a Transcription with dummy env vars and test_mode=True."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-gg")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})

    # Patch genai so google-provider services don't try to connect
    with patch("app.services.correction.genai"), patch("app.services.summarizer.genai"):
        from app.transcription import Transcription
        return Transcription(
            correct=correct,
            summarize=summarize,
            test_mode=True,
            username="test_user",
        )


# ---------------------------------------------------------------------------
# Service presence / absence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("correct,summarize,expect_corr,expect_summ", PIPELINE_COMBOS)
def test_pipeline_services_initialized(correct, summarize, expect_corr, expect_summ,
                                       tmp_config, monkeypatch):
    """Correct and summarizer services must be None XOR not-None based on flags."""
    t = _make_transcription(correct, summarize, monkeypatch, tmp_config)

    assert (t.correction_service is not None) is expect_corr, (
        f"correction_service presence mismatch for correct={correct}, summarize={summarize}"
    )
    assert (t.summary_service is not None) is expect_summ, (
        f"summary_service presence mismatch for correct={correct}, summarize={summarize}"
    )


def test_metadata_extractor_always_present_outside_test_mode(tmp_config, monkeypatch):
    """MetadataExtractorService must be initialised when test_mode=False."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    from app.transcription import Transcription
    t = Transcription(test_mode=False, username="test_user", no_db=True)
    assert t.metadata_extractor is not None


def test_metadata_extractor_absent_in_test_mode(tmp_config, monkeypatch):
    """MetadataExtractorService must be None when test_mode=True."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    from app.transcription import Transcription
    t = Transcription(test_mode=True, username="test_user")
    assert t.metadata_extractor is None


# ---------------------------------------------------------------------------
# processing_services ordering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("correct,summarize,expect_corr,expect_summ", PIPELINE_COMBOS)
def test_processing_services_order(correct, summarize, expect_corr, expect_summ,
                                   tmp_config, monkeypatch):
    """
    processing_services must be ordered:
      [metadata_extractor (if present), correction (if enabled), summarizer (if enabled)]
    """
    t = _make_transcription(correct, summarize, monkeypatch, tmp_config)

    svc_names = [type(s).__name__ for s in t.processing_services]

    # Summarizer must never appear before CorrectionService
    if expect_corr and expect_summ:
        assert svc_names.index("CorrectionService") < svc_names.index("SummarizerService")

    if expect_corr:
        assert "CorrectionService" in svc_names
    else:
        assert "CorrectionService" not in svc_names

    if expect_summ:
        assert "SummarizerService" in svc_names
    else:
        assert "SummarizerService" not in svc_names


# ---------------------------------------------------------------------------
# Pipeline stage names via _run_pipeline (using test_mode)
# ---------------------------------------------------------------------------

def test_pipeline_stage_names_are_complete(tmp_config, monkeypatch, test_audio_path):
    """After running the pipeline in test_mode, all expected stage keys must exist."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai", "nocheck": "True"})

    from app.transcription import Transcription
    t = Transcription(correct=True, summarize=True, test_mode=True, username="test_user")
    t.add_transcription_source(
        source_file=str(test_audio_path),
        title="Pipeline Stage Test",
        nocheck=True,
    )
    t.start()

    assert len(t.transcripts) == 1
    stages = t.transcripts[0].pipeline_state["stages"]
    assert set(stages.keys()) == EXPECTED_STAGE_NAMES


@pytest.mark.parametrize("correct,summarize,_,__", PIPELINE_COMBOS)
def test_pipeline_completes_successfully_in_test_mode(correct, summarize, _, __,
                                                       tmp_config, monkeypatch,
                                                       test_audio_path):
    """Pipeline must reach 'completed' overall status in test_mode."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai", "nocheck": "True"})

    with patch("app.services.correction.genai"), patch("app.services.summarizer.genai"):
        from app.transcription import Transcription
        t = Transcription(
            correct=correct,
            summarize=summarize,
            test_mode=True,
            username="test_user",
        )
        t.add_transcription_source(
            source_file=str(test_audio_path),
            title=f"Pipeline Test c={correct} s={summarize}",
            nocheck=True,
        )
        transcripts = t.start()

    assert all(tr.status == "completed" for tr in transcripts), (
        f"Not all transcripts completed: {[(tr.title, tr.status) for tr in transcripts]}"
    )
