"""
Section 5 — Output Format Tests
=================================
Autodiscovery: ``OUTPUT_FLAGS`` is a table of every output-format CLI flag
together with the key that ``ExporterFactory`` uses in the ``exporters`` dict.
Adding a new output format only requires a new row in this table.

Tests assert:
- The exporter is present in ``Transcription.exporters`` when the flag is set.
- The exporter is absent when the flag is not set.

Important: ``Transcription(test_mode=True)`` forces ``markdown=True``
(line 88 of transcription.py: ``self.markdown = markdown or test_mode``).
To test that exporters are *absent*, we must use ``test_mode=False``
(and provide a username, which test_mode normally supplies automatically).

Note on ``json``: ``ExporterFactory`` creates a json exporter when
``config.get("json", True)`` is truthy — i.e., it defaults to True unless
explicitly False.
"""

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.exporters]

# ---------------------------------------------------------------------------
# (Transcription.__init__ kwarg, exporter dict key)
# ---------------------------------------------------------------------------
OUTPUT_FLAGS = [
    pytest.param("markdown",    "markdown", id="markdown"),
    pytest.param("text_output", "text",     id="text"),
    pytest.param("json",        "json",     id="json"),
]


def _make_with_flags(monkeypatch, tmp_config, test_mode=False, **kwargs):
    """Create a Transcription with dummy env, no test_mode markdown override."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai"})
    from app.transcription import Transcription
    return Transcription(
        test_mode=test_mode,
        username="test_user",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Exporter present when flag is set
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwarg,exporter_key", OUTPUT_FLAGS)
def test_exporter_present_when_flag_set(kwarg, exporter_key, tmp_config, monkeypatch):
    """The exporter must appear in Transcription.exporters when the flag is True."""
    # test_mode=True forces markdown, so it's fine for the "present" case
    t = _make_with_flags(monkeypatch, tmp_config, test_mode=True, **{kwarg: True})
    assert exporter_key in t.exporters, (
        f"Expected '{exporter_key}' in exporters when {kwarg}=True, "
        f"but got: {list(t.exporters.keys())}"
    )


# ---------------------------------------------------------------------------
# Exporter absent when flag is not set (must NOT use test_mode=True)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwarg,exporter_key", OUTPUT_FLAGS)
def test_exporter_absent_when_flag_not_set(kwarg, exporter_key, tmp_config, monkeypatch):
    """The exporter must NOT appear when the flag is False.

    Uses test_mode=False because test_mode=True forces markdown=True in
    Transcription.__init__, making the markdown exporter always present.
    """
    t = _make_with_flags(monkeypatch, tmp_config, test_mode=False, **{kwarg: False})
    assert exporter_key not in t.exporters, (
        f"Expected '{exporter_key}' to be absent from exporters when {kwarg}=False, "
        f"but found it in: {list(t.exporters.keys())}"
    )


# ---------------------------------------------------------------------------
# Exporter type checks
# ---------------------------------------------------------------------------

def test_markdown_exporter_is_correct_type(tmp_config, monkeypatch):
    from app.exporters import MarkdownExporter
    t = _make_with_flags(monkeypatch, tmp_config, test_mode=False, markdown=True)
    assert isinstance(t.exporters["markdown"], MarkdownExporter)


def test_json_exporter_is_correct_type(tmp_config, monkeypatch):
    from app.exporters import JsonExporter
    t = _make_with_flags(monkeypatch, tmp_config, test_mode=False, json=True)
    assert isinstance(t.exporters["json"], JsonExporter)


def test_text_exporter_is_correct_type(tmp_config, monkeypatch):
    from app.exporters import TextExporter
    t = _make_with_flags(monkeypatch, tmp_config, test_mode=False, text_output=True)
    assert isinstance(t.exporters["text"], TextExporter)


# ---------------------------------------------------------------------------
# Multiple exporters can coexist
# ---------------------------------------------------------------------------

def test_multiple_exporters_can_be_enabled_simultaneously(tmp_config, monkeypatch):
    """markdown + json + text can all be active at the same time."""
    t = _make_with_flags(monkeypatch, tmp_config, test_mode=False,
                         markdown=True, json=True, text_output=True)
    assert "markdown" in t.exporters
    assert "json"     in t.exporters
    assert "text"     in t.exporters


def test_no_exporters_when_all_flags_off(tmp_config, monkeypatch):
    """When all format flags are False, exporters dict must be empty."""
    t = _make_with_flags(monkeypatch, tmp_config, test_mode=False,
                         markdown=False, json=False, text_output=False)
    assert t.exporters == {}, (
        f"Expected empty exporters dict, got: {list(t.exporters.keys())}"
    )


# ---------------------------------------------------------------------------
# Output dir propagated to exporters
# ---------------------------------------------------------------------------

def test_custom_model_output_dir_propagated(tmp_config, monkeypatch):
    """model_output_dir must be forwarded to every created exporter."""
    t = _make_with_flags(monkeypatch, tmp_config, test_mode=False,
                         markdown=True, model_output_dir="custom_output/")
    assert t.exporters["markdown"].output_dir == "custom_output/"


# ---------------------------------------------------------------------------
# test_mode forces markdown — document and pin this behaviour
# ---------------------------------------------------------------------------

def test_test_mode_forces_markdown_exporter(tmp_config, monkeypatch):
    """test_mode=True must always create a markdown exporter regardless of flag."""
    # markdown=False but test_mode=True → still present
    t = _make_with_flags(monkeypatch, tmp_config, test_mode=True, markdown=False)
    assert "markdown" in t.exporters, (
        "test_mode=True should force markdown=True in Transcription.__init__"
    )
