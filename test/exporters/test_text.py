import os

import pytest

from app.exporters import TextExporter
from app.utils import slugify


@pytest.mark.unit
@pytest.mark.exporters
class TestTextExporter:
    """Tests for the TextExporter class"""

    def test_export_basic(self, text_exporter, mock_transcript, temp_dir):
        """Test basic text export functionality"""
        # Export without timestamp
        result = text_exporter.export(mock_transcript, add_timestamp=False)

        # Check file exists
        assert os.path.exists(result)

        # Read the content
        with open(result) as f:
            content = f.read()

        # Check for transcript content
        assert content == mock_transcript.outputs["raw"]

        # Check file path
        expected_path = os.path.join(
            temp_dir, mock_transcript.source.loc, f"{slugify(mock_transcript.title)}.txt"
        )
        assert os.path.abspath(result) == os.path.abspath(expected_path)

    def test_export_with_timestamp(self, text_exporter, mock_transcript):
        """Test exporting text with timestamp in filename"""
        # Export with timestamp
        result = text_exporter.export(mock_transcript, add_timestamp=True)

        # Check file exists
        assert os.path.exists(result)

        # Check that filename includes a timestamp
        filename = os.path.basename(result)
        assert "_" in filename
        assert filename.endswith(".txt")

        # Read the content
        with open(result) as f:
            content = f.read()

        # Check for transcript content
        assert content == mock_transcript.outputs["raw"]

    def test_error_handling_no_content(self, text_exporter, mock_transcript):
        """Test error handling when transcript has no content"""
        # Set raw output to None
        mock_transcript.outputs["raw"] = None

        # Export should raise an exception
        with pytest.raises(Exception) as excinfo:
            text_exporter.export(mock_transcript)

        # Check the error message
        assert "No content found for key: raw" in str(excinfo.value)

    def test_output_directory_creation(self, temp_dir, mock_transcript):
        """Test that the exporter creates output directories as needed"""
        # Create exporter
        exporter = TextExporter(temp_dir)

        # Modify transcript location to a nested path
        mock_transcript.source.loc = "deeply/nested/path"

        # Export
        result = exporter.export(mock_transcript, add_timestamp=False)

        # Verify directory was created
        expected_dir = os.path.join(temp_dir, "deeply/nested/path")
        assert os.path.exists(expected_dir)
        assert os.path.isdir(expected_dir)

        # Verify file was created in that directory
        assert os.path.dirname(result) == os.path.abspath(expected_dir)

        # Verify file content
        with open(result) as f:
            content = f.read()
        assert content == mock_transcript.outputs["raw"]
