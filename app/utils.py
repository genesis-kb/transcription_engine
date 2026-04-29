import json
import os
import re
from datetime import date, datetime

from app.logging import get_logger


logger = get_logger()


def slugify(text):
    text = text.replace("_", "-")
    return re.sub(r"\W+", "-", text).strip("-").lower()


def decimal_to_sexagesimal(dec):
    sec = int(dec % 60)
    minu = int((dec // 60) % 60)
    hrs = int((dec // 60) // 60)

    return f"{hrs:02d}:{minu:02d}:{sec:02d}"


def check_if_valid_json(file_path):
    try:
        with open(file_path, encoding="utf-8") as file:
            json_content = json.load(file)
        return json_content
    except Exception:
        raise Exception(f"Not a valid JSON file: {file_path}")


def check_if_valid_file_path(file_path):
    if not isinstance(file_path, str) or not os.path.isfile(file_path):
        raise Exception(f"Not a valid file: {file_path}")


def validate_and_parse_date(
    date_str: str, expected_format: str = "%Y-%m-%d"
) -> date:
    """
    Validates that a given date string matches the expected date format and returns a date object.
    If the date string does not match the format, an exception is raised.
    """
    try:
        # Attempt to parse the date string using the expected format
        return datetime.strptime(date_str, expected_format).date()
    except ValueError:
        # The date string did not match the expected format
        raise Exception(
            f"The provided date '{date_str}' does not match the expected format '{expected_format}'."
        )


def configure_metadata_given_from_JSON(source, from_json=None):
    """Helper method that deals with missings fields from JSON
    by assigning default values"""
    try:
        metadata = {}
        # required in the JSON
        metadata["source_file"] = source["source_file"]
        # not required in the JSON
        metadata["title"] = source.get("title", "no-title")
        metadata["speakers"] = source.get("speakers", [])
        metadata["category"] = source.get("categories", [])
        metadata["tags"] = source.get("tags", [])
        metadata["chapters"] = source.get("chapters", [])
        metadata["loc"] = source.get("loc", "")
        metadata["date"] = source.get("date", None)
        metadata["summary"] = source.get("summary", None)
        metadata["episode"] = source.get("episode", None)
        metadata["additional_resources"] = source.get(
            "additional_resources", None
        )
        metadata["cutoff_date"] = source.get("cutoff_date", None)
        metadata["youtube_metadata"] = source.get("youtube", None)
        metadata["media"] = source.get("media", None)
        excluded_media = source.get(
            "existing_entries_not_covered_by_btctranscripts/status.json", []
        )
        metadata["excluded_media"] = [
            entry["media"] for entry in excluded_media
        ]
        # transcription service output
        services = ["whisper", "deepgram"]
        for service in services:
            key = f"{service}_output"
            metadata[key] = source.get(key, None)
            if metadata[key] is not None and from_json is not None:
                base_directory = os.path.dirname(from_json)
                metadata[key] = os.path.join(base_directory, metadata[key])
                check_if_valid_file_path(metadata[key])

        # Handle deepgram_chunks
        metadata["deepgram_chunks"] = source.get("deepgram_chunks", [])
        if metadata["deepgram_chunks"] and from_json:
            base_directory = os.path.dirname(from_json)
            metadata["deepgram_chunks"] = [
                os.path.join(base_directory, chunk)
                for chunk in metadata["deepgram_chunks"]
            ]
            for chunk_file in metadata["deepgram_chunks"]:
                check_if_valid_file_path(chunk_file)

        return metadata
    except KeyError as e:
        raise Exception(f"Parsing JSON: {e} is required")
