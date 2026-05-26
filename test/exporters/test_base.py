import json
import os

import pytest

from app.exporters import TranscriptExporter


# Create concrete subclass for testing abstract base class
class DummyExporter(TranscriptExporter):
    """Concrete implementation of TranscriptExporter for testing"""

    def export(self, transcript, **kwargs):
        """Implement abstract method for testing"""
        return self.construct_file_path(
            directory=self.get_output_path(transcript),
            filename=transcript.title,
            file_type="txt",
            include_timestamp=kwargs.get("add_timestamp", False),
        )


@pytest.mark.unit
@pytest.mark.exporters
class TestTranscriptExporter:
    """Tests for the common functionality in the TranscriptExporter base class"""

    @pytest.fixture
    def base_exporter(self, temp_dir):
        """Create an instance of the concrete subclass for testing"""
        return DummyExporter(temp_dir)

    def test_construct_file_path_with_timestamp(self, base_exporter):
        """Test file path construction with timestamp"""
        path = base_exporter.construct_file_path(
            directory=os.path.join(base_exporter.output_dir, "test"),
            filename="test_file",
            file_type="json",
            include_timestamp=True,
        )

        # Check that the path has the right elements
        assert os.path.dirname(path).endswith("test")
        assert os.path.basename(path).startswith("test_file_")
        assert path.endswith(".json")

        # Verify directory was created
        assert os.path.exists(os.path.dirname(path))

    def test_construct_file_path_without_timestamp(self, base_exporter):
        """Test file path construction without timestamp"""
        path = base_exporter.construct_file_path(
            directory=os.path.join(base_exporter.output_dir, "test"),
            filename="test_file",
            file_type="txt",
            include_timestamp=False,
        )

        # Check the path
        assert os.path.dirname(path).endswith("test")
        assert os.path.basename(path) == "test_file.txt"

        # Verify directory was created
        assert os.path.exists(os.path.dirname(path))

    def test_write_to_file_string_content(self, base_exporter, temp_dir):
        """Test writing string content to a file"""
        # Prepare test
        content = "This is test content"
        file_path = os.path.join(temp_dir, "test_string.txt")

        # Execute
        result = base_exporter.write_to_file(content, file_path)

        # Verify
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert f.read() == content
        assert result == os.path.abspath(file_path)

    def test_write_to_file_dict_content(self, base_exporter, temp_dir):
        """Test writing dictionary content to a JSON file"""
        # Prepare test
        content = {"key": "value", "nested": {"item": 123}}
        file_path = os.path.join(temp_dir, "test_dict.json")

        # Execute
        result = base_exporter.write_to_file(content, file_path)

        # Verify
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert json.load(f) == content
        assert result == os.path.abspath(file_path)

    def test_get_output_path(self, base_exporter, mock_transcript):
        """Test getting output path from transcript"""
        # Execute
        path = base_exporter.get_output_path(mock_transcript)

        # Verify
        expected_path = os.path.join(
            base_exporter.output_dir, mock_transcript.source.loc
        )
        assert path == expected_path

    def test_ensure_directory_exists(self, base_exporter, temp_dir):
        """Test directory creation"""
        # Prepare test
        test_dir = os.path.join(temp_dir, "deep", "nested", "directory")

        # Execute
        base_exporter.ensure_directory_exists(test_dir)

        # Verify
        assert os.path.exists(test_dir)
        assert os.path.isdir(test_dir)

    def test_add_timestamp(self, base_exporter):
        """Test timestamp generation for filenames"""
        # Execute
        filename = "test_file"
        timestamped = base_exporter.add_timestamp(filename)

        # Verify
        assert timestamped.startswith(filename + "_")
        assert (
            len(timestamped) > len(filename) + 15
        )  # Ensure timestamp was added
