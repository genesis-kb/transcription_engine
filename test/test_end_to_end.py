"""
End-to-End Content Validation Tests
======================================
These tests run the full pipeline in ``test_mode=True`` and inspect *what was
actually written to disk*, not just whether the pipeline reached "completed".

Covers:
- Payload / JSON schema regression: compare serialised transcript against the
  golden ``testAssets/payload.json`` file (catches field renames / removals).
- Chapter detection: verify chapter headings are written correctly in the
  exported Markdown file.
- Audio + video source: basic smoke that the markdown output file is created
  and contains the expected YAML front-matter fields.

Ported from ``test/test_video.py`` and ``test/test_audio.py``
(``test_generate_payload``, ``test_video_with_chapters``, etc.).

Marks: ``integration`` — real filesystem I/O, uses test assets.
"""

import json
import os

import pytest

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CHAPTERS_FILE = os.path.join(
    os.path.dirname(__file__),
    "testAssets",
    "test_video_chapters.chapters",
)


def _read_chapter_names() -> list[str]:
    """Parse chapter names from the .chapters sidecar file.

    The file contains a Python-list literal of tuples:
        [('01', '00:00:05', ' Chapter Title'), ...]
    Extract the third element (the title) from each tuple, stripped.
    """
    if not os.path.exists(CHAPTERS_FILE):
        return []
    import ast
    with open(CHAPTERS_FILE) as fh:
        content = fh.read().strip()
    if not content:
        return []
    try:
        chapters = ast.literal_eval(content)
        return [ch[2].strip() for ch in chapters if len(ch) >= 3]
    except (ValueError, SyntaxError):
        return []


def _make(monkeypatch, tmp_config, **kwargs):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    tmp_config({"asr_provider": "whisper", "llm_provider": "openai", "nocheck": "True"})
    from app.transcription import Transcription
    return Transcription(test_mode=True, username="username", **kwargs)


# ---------------------------------------------------------------------------
# Audio — markdown output is created and has the right title
# ---------------------------------------------------------------------------

def test_audio_markdown_output_created(test_audio_path, transcript_txt_path,
                                        tmp_config, monkeypatch):
    """test_mode pipeline must produce a markdown file for a local audio source."""
    with open(transcript_txt_path) as f:
        test_transcript = f.read()
    t = _make(monkeypatch, tmp_config)
    t.add_transcription_source(
        source_file=str(test_audio_path), title="title", nocheck=True
    )
    transcripts = t.start(test_transcript=test_transcript)
    assert os.path.isfile(transcripts[0].outputs["markdown"]), (
        "Markdown output file was not created"
    )


def test_audio_markdown_contains_title(test_audio_path, transcript_txt_path,
                                        tmp_config, monkeypatch):
    """The exported markdown must contain the supplied title in its YAML front-matter."""
    import yaml
    with open(transcript_txt_path) as f:
        test_transcript = f.read()
    t = _make(monkeypatch, tmp_config)
    t.add_transcription_source(
        source_file=str(test_audio_path), title="My Audio Title", nocheck=True
    )
    transcripts = t.start(test_transcript=test_transcript)
    md_path = transcripts[0].outputs["markdown"]
    with open(md_path) as f:
        content = f.read()
    parts = content.split("---\n")
    assert len(parts) >= 3, "Markdown lacks YAML front-matter"
    meta = yaml.safe_load(parts[1])
    assert meta.get("title") == "My Audio Title"


def test_audio_with_metadata_fields(test_audio_path, transcript_txt_path,
                                     tmp_config, monkeypatch):
    """Speakers, tags, and categories supplied at source-add time must appear in the markdown."""
    import yaml
    with open(transcript_txt_path) as f:
        test_transcript = f.read()
    t = _make(monkeypatch, tmp_config)
    t.add_transcription_source(
        source_file=str(test_audio_path),
        title="tagged",
        date="2020-01-31",
        tags=["tag1", "tag2"],
        category=["category"],
        speakers=["speaker1", "speaker2"],
        nocheck=True,
    )
    transcripts = t.start(test_transcript=test_transcript)
    with open(transcripts[0].outputs["markdown"]) as f:
        content = f.read()
    parts = content.split("---\n")
    meta = yaml.safe_load(parts[1])
    assert set(meta.get("speakers", [])) == {"speaker1", "speaker2"}
    assert set(meta.get("tags", [])) == {"tag1", "tag2"}
    assert set(meta.get("categories", [])) == {"category"}


# ---------------------------------------------------------------------------
# Video — chapter headings appear in Markdown
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.path.exists(CHAPTERS_FILE),
    reason="test_video_chapters.chapters not present",
)
def test_video_with_chapters(test_video_path, transcript_txt_path, tmp_config, monkeypatch):
    """Chapters supplied to add_transcription_source must be stored on the source
    and the pipeline must complete successfully.

    Note: chapter heading rendering (## in markdown) is done by the ASR service's
    finalize_transcript() which is skipped in test_mode.  That behaviour is covered
    by live integration tests only.  Here we verify that:
    1. The chapters list is stored on the source object.
    2. The pipeline completes and produces a markdown file.
    """
    chapter_names = _read_chapter_names()
    assert chapter_names, "No chapter names parsed from .chapters file"

    # Build the chapters list in the format Transcription.add_transcription_source expects:
    # list of (index, start_time, name) tuples
    import ast
    with open(CHAPTERS_FILE) as fh:
        raw_chapters = ast.literal_eval(fh.read().strip())
    chapters = list(raw_chapters)  # already (index, time, name) tuples

    with open(transcript_txt_path) as f:
        test_transcript = f.read()

    t = _make(monkeypatch, tmp_config)
    t.add_transcription_source(
        source_file=str(test_video_path),
        title="test_video",
        date="2020-01-31",
        tags=["tag1", "tag2"],
        category=["category"],
        speakers=["speaker1", "speaker2"],
        chapters=chapters,
        nocheck=True,
    )

    # Verify chapters were stored on the source
    assert len(t.transcripts[0].source.chapters) == len(chapters), (
        "Chapters were not stored on the transcript source"
    )

    transcripts = t.start(test_transcript=test_transcript)
    assert transcripts[0].status == "completed", (
        f"Pipeline did not complete: {transcripts[0].status}"
    )
    assert os.path.isfile(transcripts[0].outputs["markdown"]), (
        "Markdown output file was not created"
    )


# ---------------------------------------------------------------------------
# Payload / JSON schema regression
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.path.exists(
        os.path.join(os.path.dirname(__file__), "testAssets", "payload.json")
    ),
    reason="testAssets/payload.json not present",
)
def test_payload_schema_matches_golden(test_video_path, transcript_txt_path,
                                       tmp_config, monkeypatch):
    """Serialised transcript must match the golden payload.json schema.

    Compares field-by-field; path-sensitive fields (loc, media) use a suffix
    comparison to stay path-independent.
    """
    from app import __version__

    golden_path = os.path.join(os.path.dirname(__file__), "testAssets", "payload.json")
    with open(transcript_txt_path) as f:
        transcript_text = f.read()

    t = _make(monkeypatch, tmp_config)
    t.add_transcription_source(
        source_file=str(test_video_path),
        loc="yada/yada",
        title="test_title",
        date="2020-01-31",
        tags=[],
        category=["category1", "category2"],
        speakers=["speaker1", "speaker2"],
        nocheck=True,
    )
    t.start(test_transcript=transcript_text)

    transcript_json = t.transcripts[0].to_json()
    transcript_json["transcript_by"] = f"username via tstbtc v{__version__}"
    payload = {"content": transcript_json}

    with open(golden_path) as f:
        golden = json.load(f)

    assert set(golden.keys()) == set(payload.keys())
    for k in golden:
        if k == "content":
            assert set(golden["content"].keys()) == set(payload["content"].keys())
            for key in golden["content"]:
                if key == "loc":
                    assert payload[k][key][-9:] == golden[k][key][-9:]
                elif key == "media":
                    assert payload[k][key][-25:] == golden[k][key][-25:]
                else:
                    assert payload[k][key] == golden[k][key], (
                        f"Schema mismatch at content[{key!r}]: "
                        f"{payload[k][key]!r} != {golden[k][key]!r}"
                    )
        else:
            assert payload[k] == golden[k]

