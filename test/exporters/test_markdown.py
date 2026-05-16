import os

import pytest
import yaml

from app.utils import slugify


@pytest.mark.unit
@pytest.mark.exporters
class TestMarkdownExporter:
    """Tests for the MarkdownExporter class"""

    def test_export_with_metadata(
        self, markdown_exporter, mock_transcript, temp_dir
    ):
        """Test exporting markdown with metadata"""
        # Export with metadata
        result = markdown_exporter.export(
            mock_transcript,
            include_metadata=True,
            add_timestamp=False,
            version="1.0.0",
            review_flag=" --needs-review",
        )

        # Check file exists
        assert os.path.exists(result)

        # Read the content
        with open(result) as f:
            content = f.read()

        # Check for YAML frontmatter
        assert content.startswith("---")
        assert (
            "transcript_by: Test User via tstbtc v1.0.0 --needs-review"
            in content
        )
        assert "---" in content

        # Check for transcript content
        assert "This is a test transcript." in content

        # Verify the file path
        assert os.path.basename(result).startswith(slugify(mock_transcript.title))
        assert result.endswith(".md")

    def test_export_without_metadata(
        self, markdown_exporter, mock_transcript, temp_dir
    ):
        """Test exporting markdown without metadata"""
        # Export without metadata
        result = markdown_exporter.export(
            mock_transcript, include_metadata=False, add_timestamp=False
        )

        # Check file exists and has the right name
        assert os.path.exists(result)
        assert "_plain.md" in result

        # Read the content
        with open(result) as f:
            content = f.read()

        # Check for absence of YAML frontmatter
        assert not content.startswith("---")

        # Check for presence of transcript content only
        assert content == mock_transcript.outputs["raw"]

    def test_yaml_metadata_formatting(self, markdown_exporter, mock_transcript):
        """Test that YAML metadata is properly formatted"""
        # Directly test the _create_with_metadata method
        content = markdown_exporter._create_with_metadata(
            mock_transcript, version="1.0.0", review_flag=""
        )

        # Extract just the YAML part
        yaml_part = content.split("---")[1]

        # Parse the YAML to verify it's valid
        metadata = yaml.safe_load(yaml_part)

        # Check that metadata contains expected keys
        assert "title" in metadata
        assert "speakers" in metadata
        assert "tags" in metadata
        assert "transcript_by" in metadata

        # Check that excluded fields are not present
        assert "type" not in metadata
        assert "loc" not in metadata
        assert "chapters" not in metadata

        # Check that lists are properly formatted (this would depend on your YAML formatter)
        assert isinstance(metadata["speakers"], list)
        assert isinstance(metadata["tags"], list)

    def test_error_handling_no_content(
        self, markdown_exporter, mock_transcript
    ):
        """Test that exporter handles missing content properly"""
        # Set raw output to None
        mock_transcript.outputs["raw"] = None

        # Export should raise an exception
        with pytest.raises(Exception) as excinfo:
            markdown_exporter.export(mock_transcript)

        # Check the error message
        assert "No transcript content found" in str(excinfo.value)
