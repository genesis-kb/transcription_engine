import json
import os
from datetime import datetime, timezone
from typing import Literal


class DataWriter:
    """
    The DataWriter class is responsible for managing all file writing operations within the application.
    It provides a centralized mechanism to write data files, into a structured directory hierarchy.
    This class ensures that all data writes are handled uniformly, supporting maintainability
    and scalability of file management operations.
    """

    def __init__(self, base_dir):
        """
        Initializes the DataWriter instance with a basedirectory where all files will be saved.
        """
        self.base_dir = base_dir

    def add_timestamp(self, filename):
        """
        Appends a UTC timestamp to a filename to ensure uniqueness and traceability
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        return f"{filename}_{timestamp}"

    def write_json(self, data, file_path, filename, include_timestamp=True):
        """
        Writes given data to a JSON file, organizing it within the
        structured directory path based on `file_path` and `filename`
        """
        output_file = self.construct_file_path(
            file_path,
            filename,
            type="json",
            include_timestamp=include_timestamp,
        )
        with open(output_file, "w", encoding="utf-8") as json_file:
            json.dump(data, json_file, indent=4)
        return output_file

    def construct_file_path(
        self,
        file_path,
        filename,
        type: Literal["json", "srt"],
        include_timestamp=True,
    ):
        """
        Constructs the full file path for the data file, creating necessary
        directories and appending a timestamp and file type to the filename
        """
        target_file_path = os.path.join(self.base_dir, file_path)
        os.makedirs(target_file_path, exist_ok=True)
        filename = f"{self.add_timestamp(filename) if include_timestamp else filename}.{type}"
        return os.path.join(target_file_path, filename)
