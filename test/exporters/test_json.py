import json
import os

import pytest

from app.exporters import JsonExporter
from app.utils import slugify


@pytest.mark.unit
@pytest.mark.exporters
class TestJsonExporter:
    """Tests for the JsonExporter class"""

    def test_export_with_attribution(
        self, json_exporter, mock_transcript, temp_dir
    ):
        """Test exporting JSON with attribution"""
        # Export with attribution
        result = json_exporter.export(
            mock_transcript, add_timestamp=False, version="1.0.0"
        )

        # Check file exists
        assert os.path.exists(result)

        # Read the content
        with open(result) as f:
            content = json.load(f)

        # Check for transcript data
        assert content["title"] == mock_transcript.title
        assert content["transcript_by"] == "Test User via tstbtc v1.0.0"

        # Check file path
        expected_path = os.path.join(
            temp_dir,
            mock_transcript.source.loc,
            f"{slugify(mock_transcript.title)}.json",
        )
        assert os.path.abspath(result) == os.path.abspath(expected_path)

    def test_export_without_attribution(self, temp_dir, mock_transcript):
        """Test exporting JSON without attribution"""
        # Create exporter without transcript_by
        exporter = JsonExporter(temp_dir, transcript_by=None)

        # Export without attribution
        result = exporter.export(mock_transcript, add_timestamp=False)

        # Check file exists
        assert os.path.exists(result)

        # Read the content
        with open(result) as f:
            content = json.load(f)

        # Check for transcript data
        assert content["title"] == mock_transcript.title
        assert "transcript_by" not in content

    def test_content_structure(self, json_exporter, mock_transcript):
        """Test the structure of the exported JSON content"""
        # Export
        result = json_exporter.export(
            mock_transcript, add_timestamp=False, version="1.0.0"
        )

        # Read the content
        with open(result) as f:
            content = json.load(f)

        # Check for required fields from transcript.to_json()
        assert "title" in content
        assert "speakers" in content
        assert "tags" in content
        assert "categories" in content
        assert "loc" in content

        # Check that the content matches what transcript.to_json() should return
        expected_json = mock_transcript.to_json()
        for key, value in expected_json.items():
            assert content[key] == value, f"JSON content mismatch for key {key}"

        # Check that transcript_by was added
        assert content["transcript_by"] == "Test User via tstbtc v1.0.0"
