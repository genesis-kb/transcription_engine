"""
Exporter Unit Tests
====================
Covers:
- ``TranscriptExporter`` base class (file path construction, write helpers)
- ``MarkdownExporter``  — with/without YAML front-matter, error handling
- ``JsonExporter``      — attribution, content structure
- ``TextExporter``      — basic, timestamp, error, nested dirs
- ``ExporterFactory``   — all combinations, custom dir, transcript_by=None

Ported from ``test/exporters/`` (test_base.py, test_markdown.py,
test_json.py, test_text.py, test_factory.py).

Fixtures: ``temp_dir``, ``mock_transcript``, ``markdown_exporter``,
          ``json_exporter``, ``text_exporter`` — all in conftest.py.
"""

import json
import os

import pytest
import yaml

from app.exporters import (
    ExporterFactory,
    JsonExporter,
    MarkdownExporter,
    TextExporter,
    TranscriptExporter,
)

pytestmark = [pytest.mark.unit, pytest.mark.exporters]


# ===========================================================================
# Helpers
# ===========================================================================

class _TestableExporter(TranscriptExporter):
    """Minimal concrete subclass used to exercise the abstract base class."""

    def export(self, transcript, **kwargs):
        return self.construct_file_path(
            directory=self.get_output_path(transcript),
            filename=transcript.title,
            file_type="txt",
            include_timestamp=kwargs.get("add_timestamp", False),
        )


# ===========================================================================
# TranscriptExporter base class
# ===========================================================================

@pytest.mark.unit
@pytest.mark.exporters
class TestTranscriptExporter:
    """Tests for the shared functionality in TranscriptExporter."""

    @pytest.fixture
    def base_exporter(self, temp_dir):
        return _TestableExporter(temp_dir)

    def test_construct_file_path_with_timestamp(self, base_exporter):
        path = base_exporter.construct_file_path(
            directory=os.path.join(base_exporter.output_dir, "test"),
            filename="test_file",
            file_type="json",
            include_timestamp=True,
        )
        assert os.path.dirname(path).endswith("test")
        assert os.path.basename(path).startswith("test_file_")
        assert path.endswith(".json")
        assert os.path.exists(os.path.dirname(path))

    def test_construct_file_path_without_timestamp(self, base_exporter):
        path = base_exporter.construct_file_path(
            directory=os.path.join(base_exporter.output_dir, "test"),
            filename="test_file",
            file_type="txt",
            include_timestamp=False,
        )
        assert os.path.dirname(path).endswith("test")
        assert os.path.basename(path) == "test_file.txt"
        assert os.path.exists(os.path.dirname(path))

    def test_write_to_file_string_content(self, base_exporter, temp_dir):
        content = "This is test content"
        file_path = os.path.join(temp_dir, "test_string.txt")
        result = base_exporter.write_to_file(content, file_path)
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert f.read() == content
        assert result == os.path.abspath(file_path)

    def test_write_to_file_dict_content(self, base_exporter, temp_dir):
        content = {"key": "value", "nested": {"item": 123}}
        file_path = os.path.join(temp_dir, "test_dict.json")
        result = base_exporter.write_to_file(content, file_path)
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert json.load(f) == content
        assert result == os.path.abspath(file_path)

    def test_get_output_path(self, base_exporter, mock_transcript):
        path = base_exporter.get_output_path(mock_transcript)
        expected = os.path.join(base_exporter.output_dir, mock_transcript.source.loc)
        assert path == expected

    def test_ensure_directory_exists(self, base_exporter, temp_dir):
        test_dir = os.path.join(temp_dir, "deep", "nested", "directory")
        base_exporter.ensure_directory_exists(test_dir)
        assert os.path.exists(test_dir)
        assert os.path.isdir(test_dir)

    def test_add_timestamp(self, base_exporter):
        filename = "test_file"
        timestamped = base_exporter.add_timestamp(filename)
        assert timestamped.startswith(filename + "_")
        assert len(timestamped) > len(filename) + 15


# ===========================================================================
# MarkdownExporter
# ===========================================================================

@pytest.mark.unit
@pytest.mark.exporters
class TestMarkdownExporter:
    """Tests for MarkdownExporter."""

    def test_export_with_metadata(self, markdown_exporter, mock_transcript, temp_dir):
        result = markdown_exporter.export(
            mock_transcript,
            include_metadata=True,
            add_timestamp=False,
            version="1.0.0",
            review_flag=" --needs-review",
        )
        assert os.path.exists(result)
        with open(result) as f:
            content = f.read()
        assert content.startswith("---")
        assert "transcript_by: Test User via tstbtc v1.0.0 --needs-review" in content
        assert "This is a test transcript." in content
        # The exporter slugifies the title ("Test Transcript" → "test-transcript")
        basename = os.path.basename(result)
        assert "transcript" in basename.lower()
        assert result.endswith(".md")

    def test_export_without_metadata(self, markdown_exporter, mock_transcript):
        result = markdown_exporter.export(
            mock_transcript, include_metadata=False, add_timestamp=False
        )
        assert os.path.exists(result)
        assert "_plain.md" in result
        with open(result) as f:
            content = f.read()
        assert not content.startswith("---")
        assert content == mock_transcript.outputs["raw"]

    def test_yaml_metadata_formatting(self, markdown_exporter, mock_transcript):
        content = markdown_exporter._create_with_metadata(
            mock_transcript, version="1.0.0", review_flag=""
        )
        yaml_part = content.split("---")[1]
        metadata = yaml.safe_load(yaml_part)
        assert "title" in metadata
        assert "speakers" in metadata
        assert "tags" in metadata
        assert "transcript_by" in metadata
        assert "type" not in metadata
        assert "loc" not in metadata
        assert "chapters" not in metadata
        assert isinstance(metadata["speakers"], list)
        assert isinstance(metadata["tags"], list)

    def test_error_handling_no_content(self, markdown_exporter, mock_transcript):
        mock_transcript.outputs["raw"] = None
        with pytest.raises(Exception, match="No transcript content found"):
            markdown_exporter.export(mock_transcript)



# ===========================================================================
# JsonExporter
# ===========================================================================

@pytest.mark.unit
@pytest.mark.exporters
class TestJsonExporter:
    """Tests for JsonExporter."""

    def test_export_with_attribution(self, json_exporter, mock_transcript, temp_dir):
        result = json_exporter.export(mock_transcript, add_timestamp=False, version="1.0.0")
        assert os.path.exists(result)
        with open(result) as f:
            content = json.load(f)
        assert content["title"] == mock_transcript.title
        assert content["transcript_by"] == "Test User via tstbtc v1.0.0"
        # Verify the file lives in the expected directory (title may be slugified)
        expected_dir = os.path.join(temp_dir, mock_transcript.source.loc)
        assert os.path.dirname(os.path.abspath(result)) == os.path.abspath(expected_dir)
        assert result.endswith(".json")

    def test_export_without_attribution(self, temp_dir, mock_transcript):
        exporter = JsonExporter(temp_dir, transcript_by=None)
        result = exporter.export(mock_transcript, add_timestamp=False)
        assert os.path.exists(result)
        with open(result) as f:
            content = json.load(f)
        assert content["title"] == mock_transcript.title
        assert "transcript_by" not in content

    def test_content_structure(self, json_exporter, mock_transcript):
        result = json_exporter.export(mock_transcript, add_timestamp=False, version="1.0.0")
        with open(result) as f:
            content = json.load(f)
        for key in ["title", "speakers", "tags", "categories", "loc"]:
            assert key in content
        expected = mock_transcript.to_json()
        for key, value in expected.items():
            assert content[key] == value
        assert content["transcript_by"] == "Test User via tstbtc v1.0.0"


# ===========================================================================
# TextExporter
# ===========================================================================

@pytest.mark.unit
@pytest.mark.exporters
class TestTextExporter:
    """Tests for TextExporter."""

    def test_export_basic(self, text_exporter, mock_transcript, temp_dir):
        result = text_exporter.export(mock_transcript, add_timestamp=False)
        assert os.path.exists(result)
        with open(result) as f:
            content = f.read()
        assert content == mock_transcript.outputs["raw"]
        # Verify the file lives in the expected directory (title may be slugified)
        expected_dir = os.path.join(temp_dir, mock_transcript.source.loc)
        assert os.path.dirname(os.path.abspath(result)) == os.path.abspath(expected_dir)
        assert result.endswith(".txt")

    def test_export_with_timestamp(self, text_exporter, mock_transcript):
        result = text_exporter.export(mock_transcript, add_timestamp=True)
        assert os.path.exists(result)
        filename = os.path.basename(result)
        assert "_" in filename
        assert filename.endswith(".txt")
        with open(result) as f:
            content = f.read()
        assert content == mock_transcript.outputs["raw"]

    def test_error_handling_no_content(self, text_exporter, mock_transcript):
        mock_transcript.outputs["raw"] = None
        with pytest.raises(Exception, match="No content found for key: raw"):
            text_exporter.export(mock_transcript)


    def test_output_directory_creation(self, temp_dir, mock_transcript):
        exporter = TextExporter(temp_dir)
        mock_transcript.source.loc = "deeply/nested/path"
        result = exporter.export(mock_transcript, add_timestamp=False)
        expected_dir = os.path.join(temp_dir, "deeply/nested/path")
        assert os.path.exists(expected_dir)
        assert os.path.isdir(expected_dir)
        assert os.path.dirname(result) == os.path.abspath(expected_dir)
        with open(result) as f:
            content = f.read()
        assert content == mock_transcript.outputs["raw"]


# ===========================================================================
# ExporterFactory
# ===========================================================================

@pytest.mark.unit
@pytest.mark.exporters
class TestExporterFactory:
    """Tests for ExporterFactory.create_exporters."""

    def test_create_all_exporters(self, temp_dir):
        config = {"markdown": True, "text_output": True, "json": True,
                  "model_output_dir": temp_dir}
        exporters = ExporterFactory.create_exporters(config=config, transcript_by="Test User")
        assert "markdown" in exporters
        assert "text" in exporters
        assert "json" in exporters
        assert isinstance(exporters["markdown"], MarkdownExporter)
        assert isinstance(exporters["text"], TextExporter)
        assert isinstance(exporters["json"], JsonExporter)
        assert exporters["markdown"].transcript_by == "Test User"
        assert exporters["json"].transcript_by == "Test User"
        assert exporters["markdown"].output_dir == temp_dir
        assert exporters["text"].output_dir == temp_dir
        assert exporters["json"].output_dir == temp_dir

    def test_create_partial_exporters(self, temp_dir):
        config = {"markdown": True, "text_output": False, "json": False,
                  "model_output_dir": temp_dir}
        exporters = ExporterFactory.create_exporters(config=config, transcript_by="Test User")
        assert "markdown" in exporters
        assert "text" not in exporters
        assert "json" not in exporters
        assert isinstance(exporters["markdown"], MarkdownExporter)

    def test_no_exporters(self, temp_dir):
        config = {"markdown": False, "text_output": False, "json": False,
                  "model_output_dir": temp_dir}
        exporters = ExporterFactory.create_exporters(config=config, transcript_by="Test User")
        assert not exporters
        assert isinstance(exporters, dict)

    def test_custom_output_dir(self):
        custom_dir = "/custom/output/dir"
        config = {"markdown": True, "text_output": True, "json": True,
                  "model_output_dir": custom_dir}
        exporters = ExporterFactory.create_exporters(config=config, transcript_by="Test User")
        assert exporters["markdown"].output_dir == custom_dir
        assert exporters["text"].output_dir == custom_dir
        assert exporters["json"].output_dir == custom_dir

    def test_transcript_by_none(self, temp_dir):
        config = {"markdown": True, "text_output": True, "json": True,
                  "model_output_dir": temp_dir}
        exporters = ExporterFactory.create_exporters(config=config, transcript_by=None)
        assert exporters["markdown"].transcript_by is None
        assert exporters["json"].transcript_by is None
