import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Literal, Union

import yaml

from app import __version__
from app.logging import get_logger
from app.transcript import Transcript
from app.utils import slugify


class TranscriptExporter(ABC):
    """
    Base class for all transcript exporters.

    Exporters are responsible for taking a transcript and outputting it in a specific format
    to a specific destination.
    """

    def __init__(self, output_dir: str):
        """
        Initialize the exporter with an output directory.

        Args:
            output_dir: The base directory where exports will be saved
        """
        self.output_dir = output_dir
        self.logger = get_logger()

    @abstractmethod
    def export(self, transcript: Transcript, **kwargs) -> str:
        """
        Export the transcript in the format specific to this exporter.

        Args:
            transcript: The transcript to export
            **kwargs: Additional format-specific parameters

        Returns:
            The path to the exported file
        """
        pass

    def get_output_path(self, transcript: Transcript) -> str:
        """
        Get the output path for this transcript based on its location.

        Args:
            transcript: The transcript to get the path for

        Returns:
            The directory path where the transcript should be exported
        """
        return os.path.join(self.output_dir, transcript.source.loc)

    def ensure_directory_exists(self, directory: str) -> None:
        """
        Ensure the specified directory exists, creating it if necessary.

        Args:
            directory: The directory path to check/create
        """
        os.makedirs(directory, exist_ok=True)

    def add_timestamp(self, filename: str) -> str:
        """
        Add a timestamp to a filename for uniqueness.

        Args:
            filename: The filename without timestamp

        Returns:
            The filename with timestamp added
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        return f"{filename}_{timestamp}"

    def construct_file_path(
        self,
        directory: str,
        filename: str,
        file_type: Literal["json", "md", "txt", "srt", "html"],
        include_timestamp: bool = True,
    ) -> str:
        """
        Construct a file path with proper directory, filename, and extension.

        Args:
            directory: The directory to place the file in
            filename: The base filename
            file_type: The file extension/type
            include_timestamp: Whether to add a timestamp to the filename

        Returns:
            The complete file path
        """
        self.ensure_directory_exists(directory)
        if include_timestamp:
            filename = self.add_timestamp(filename)
        return os.path.join(directory, f"{filename}.{file_type}")

    def write_to_file(
        self, content: Union[str, dict[str, Any]], file_path: str
    ) -> str:
        """
        Write content to a file based on file extension.

        Args:
            content: The content to write (string or dictionary)
            file_path: The full path to the file

        Returns:
            The absolute path to the written file
        """
        try:
            # Handle different content types based on file extension
            if file_path.endswith(".json") and isinstance(content, dict):
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(content, f, indent=4)
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

            return os.path.abspath(file_path)

        except Exception as e:
            self.logger.error(f"Error writing to file {file_path}: {e}")
            raise


class MarkdownExporter(TranscriptExporter):
    """
    Exporter for Markdown format with optional YAML frontmatter.
    """

    def __init__(self, output_dir: str, transcript_by: str = None):
        """
        Initialize the Markdown exporter.

        Args:
            output_dir: The base directory where exports will be saved
            transcript_by: Attribution string for the transcript
        """
        super().__init__(output_dir)
        self.transcript_by = transcript_by

    def export(self, transcript: Transcript, **kwargs) -> str:
        """
        Export the transcript as a Markdown file.

        Args:
            transcript: The transcript to export
            include_metadata: Whether to include YAML frontmatter (default: True)
            add_timestamp: Whether to add a timestamp to the filename (default: False)
            **kwargs: Additional parameters like review_flag, version

        Returns:
            The path to the exported Markdown file
        """
        self.logger.debug("Exporting transcript to Markdown...")

        if transcript.outputs["raw"] is None:
            raise Exception("No transcript content found")

        # Get parameters
        include_metadata = kwargs.get("include_metadata", True)
        add_timestamp = kwargs.get("add_timestamp", False)

        # Get output directory
        output_dir = self.get_output_path(transcript)

        # Generate content with or without metadata
        if include_metadata:
            content = self._create_with_metadata(transcript, **kwargs)
            suffix = ""
        else:
            content = transcript.outputs["raw"]
            suffix = "_plain"

        # Construct file path
        file_path = self.construct_file_path(
            directory=output_dir,
            filename=f"{slugify(transcript.title)}{suffix}",
            file_type="md",
            include_timestamp=add_timestamp,
        )

        # Write to file
        result_path = self.write_to_file(content, file_path)

        self.logger.info(f"(exporter) Markdown file written to: {result_path}")
        return result_path

    def _create_with_metadata(self, transcript: Transcript, **kwargs) -> str:
        """
        Create Markdown content with YAML frontmatter metadata.

        Args:
            transcript: The transcript to export
            **kwargs: Additional parameters like review_flag and content_key

        Returns:
            The complete Markdown content with metadata
        """

        class IndentedListDumper(yaml.Dumper):
            """Custom YAML Dumper that ensures lists are always indented."""

            def increase_indent(self, flow=False, indentless=False):
                return super(IndentedListDumper, self).increase_indent(
                    flow, False
                )

        # Get metadata from the source
        metadata = transcript.source.to_json()

        # Determine which content to use
        content_key = kwargs.get("content_key", "corrected_text")
        content = transcript.outputs.get(
            content_key, transcript.outputs.get("raw")
        )

        if content is None:
            raise Exception(
                f"No transcript content found for key '{content_key}' or 'raw'"
            )

        # Add or modify specific fields
        if self.transcript_by:
            review_flag = kwargs.get("review_flag", "")
            version = kwargs.get("version", __version__)
            metadata["transcript_by"] = (
                f"{self.transcript_by} via tstbtc v{version}{review_flag}"
            )

        # List of fields to exclude from the markdown metadata
        excluded_fields = ["type", "loc", "chapters", "description"]

        # Remove excluded fields
        for field in excluded_fields:
            metadata.pop(field, None)

        # Convert metadata to YAML
        yaml_metadata = yaml.dump(
            metadata, Dumper=IndentedListDumper, sort_keys=False
        )

        # Combine metadata and content
        return f"---\n{yaml_metadata}---\n\n{transcript.outputs['raw']}\n"


class JsonExporter(TranscriptExporter):
    """
    Exporter for JSON format.
    """

    def __init__(self, output_dir: str, transcript_by: str = None):
        """
        Initialize the JSON exporter.

        Args:
            output_dir: The base directory where exports will be saved
            transcript_by: Attribution string for the transcript
        """
        super().__init__(output_dir)
        self.transcript_by = transcript_by

    def export(self, transcript: Transcript, **kwargs) -> str:
        """
        Export the transcript as a JSON file.

        Args:
            transcript: The transcript to export
            add_timestamp: Whether to add a timestamp to the filename (default: True)
            **kwargs: Additional parameters like version

        Returns:
            The path to the exported JSON file
        """
        self.logger.debug("Exporting transcript to JSON...")

        # Get parameters
        add_timestamp = kwargs.get("add_timestamp", False)

        # Get output directory
        output_dir = self.get_output_path(transcript)

        # Prepare the data
        transcript_json = transcript.to_json()

        # Add attribution if provided
        if self.transcript_by:
            version = kwargs.get("version", __version__)
            transcript_json["transcript_by"] = (
                f"{self.transcript_by} via tstbtc v{version}"
            )

        # Construct file path
        file_path = self.construct_file_path(
            directory=output_dir,
            filename=slugify(transcript.title),
            file_type="json",
            include_timestamp=add_timestamp,
        )

        # Write to file
        result_path = self.write_to_file(transcript_json, file_path)

        self.logger.info(f"(exporter) JSON file written to: {result_path}")
        return result_path


class TextExporter(TranscriptExporter):
    """
    Exporter for plain text format (no metadata).
    """

    def export(self, transcript: Transcript, **kwargs) -> str:
        """
        Export the transcript as a plain text file.

        Args:
            transcript: The transcript to export
            add_timestamp: Whether to add a timestamp to the filename (default: False)
            content_key: The key in transcript.outputs to use for the content (default: "raw")
            suffix: A suffix to add to the filename (e.g., "_raw")
            **kwargs: Additional parameters (unused)

        Returns:
            The path to the exported text file
        """
        self.logger.debug("Exporting transcript to plain text...")

        content_key = kwargs.get("content_key", "raw")
        content = transcript.outputs.get(content_key)
        if content is None and content_key == "summary":
            content = transcript.summary

        if content is None:
            raise Exception(f"No content found for key: {content_key}")

        # Get parameters
        add_timestamp = kwargs.get("add_timestamp", False)
        suffix = kwargs.get("suffix", "")

        # Get output directory
        output_dir = self.get_output_path(transcript)

        # Construct file path
        file_path = self.construct_file_path(
            directory=output_dir,
            filename=f"{slugify(transcript.title)}{suffix}",
            file_type="txt",
            include_timestamp=add_timestamp,
        )

        # Write to file
        result_path = self.write_to_file(content, file_path)

        self.logger.info(f"(exporter) Text file written to: {result_path}")
        return result_path


class ExporterFactory:
    """
    Factory class for creating exporters based on configuration.
    """

    @staticmethod
    def create_exporters(
        config: dict[str, Any], transcript_by: str = None
    ) -> dict[str, TranscriptExporter]:
        """
        Create exporters based on the provided configuration.

        Args:
            config: A dictionary containing export configuration
            transcript_by: Attribution string for the transcript

        Returns:
            A dictionary of exporters with their type as the key
        """
        exporters = {}
        output_dir = config.get("model_output_dir", "local_models/")

        # Create markdown exporter if needed
        if config.get("markdown", False):
            exporters["markdown"] = MarkdownExporter(
                output_dir=output_dir,
                transcript_by=transcript_by,
            )

        # Create text exporter if needed
        if config.get("text_output", False):
            exporters["text"] = TextExporter(output_dir=output_dir)

        # Create JSON exporter if needed
        if config.get("json", True):
            exporters["json"] = JsonExporter(
                output_dir=output_dir,
                transcript_by=transcript_by,
            )

        return exporters
