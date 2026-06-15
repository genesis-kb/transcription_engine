"""Input file parser for the audiobook curation pipeline.

Reads text files with YAML frontmatter metadata from an input directory.
Supports two input types:
  - single_article: standalone content (newsletter, blog post)
  - series: one page of a multi-page guide (e.g. learnmeabitcoin)

Expected file format:
    ---
    type: series
    series_slug: learn-me-a-bitcoin
    series_title: Learn Me a Bitcoin
    sequence_number: 1
    title: Introduction
    ---
    Body text here...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from app.logging import get_logger


logger = get_logger()

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class InputFile:
    """Parsed representation of a single input text file."""

    filepath: Path
    input_type: str              # 'single_article' or 'series'
    title: str
    body: str

    # Series-specific fields
    series_slug: Optional[str] = None
    series_title: Optional[str] = None
    sequence_number: int = 1

    # Common optional fields
    author: Optional[str] = None
    source_url: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.body.split())


def _parse_tags(raw_tags: object) -> list[str]:
    if not raw_tags:
        return []
    if isinstance(raw_tags, str):
        return [raw_tags]
    if isinstance(raw_tags, list):
        return [str(t) for t in raw_tags]
    return [str(raw_tags)]


def parse_file(filepath: Path) -> Optional[InputFile]:
    """Parse a single text file with YAML frontmatter.

    Returns None if the file cannot be parsed or has no valid metadata.
    """
    try:
        raw = filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Cannot read file {filepath}: {e}")
        return None

    match = FRONTMATTER_RE.match(raw)
    if not match:
        # No frontmatter — treat as a plain single article
        body = raw.strip()
        if not body:
            logger.warning(f"Empty body in {filepath.name}, skipping")
            return None

        logger.info(
            f"No YAML frontmatter in {filepath.name}, "
            "treating as single_article"
        )
        return InputFile(
            filepath=filepath,
            input_type="single_article",
            title=filepath.stem.replace("_", " ").replace("-", " ").title(),
            body=body,
        )

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML frontmatter in {filepath.name}: {e}")
        return None

    body = raw[match.end():].strip()
    if not body:
        logger.warning(f"Empty body in {filepath.name}, skipping")
        return None

    input_type = meta.get("type", "single_article")
    title = meta.get("title", filepath.stem.replace("_", " ").title())

    if input_type == "series":
        if not meta.get("series_slug"):
            logger.error(
                f"Series file {filepath.name} missing 'series_slug', "
                "skipping"
            )
            return None
        return InputFile(
            filepath=filepath,
            input_type="series",
            title=title,
            body=body,
            series_slug=meta["series_slug"],
            series_title=meta.get("series_title", title),
            sequence_number=int(meta.get("sequence_number", 1)),
            author=meta.get("author"),
            source_url=meta.get("source_url"),
            description=meta.get("description"),
            tags=_parse_tags(meta.get("tags")),
        )

    # single_article (default)
    return InputFile(
        filepath=filepath,
        input_type="single_article",
        title=title,
        body=body,
        author=meta.get("author"),
        source_url=meta.get("source_url"),
        description=meta.get("description"),
        tags=_parse_tags(meta.get("tags")),
    )


def scan_input_directory(input_dir: str | Path) -> list[InputFile]:
    """Scan a directory for .txt files and parse each one.

    Returns a list of successfully parsed InputFile objects.
    """
    input_path = Path(input_dir)
    if not input_path.is_dir():
        logger.error(f"Input directory does not exist: {input_path}")
        return []

    files = sorted(input_path.glob("*.txt"))
    if not files:
        logger.info(f"No .txt files found in {input_path}")
        return []

    parsed: list[InputFile] = []
    for f in files:
        result = parse_file(f)
        if result:
            parsed.append(result)

    logger.info(
        f"Scanned {len(files)} file(s), "
        f"parsed {len(parsed)} successfully"
    )
    return parsed


def group_series(inputs: list[InputFile]) -> dict[str, list[InputFile]]:
    """Group series-type InputFiles by their series_slug.

    Returns a dict mapping series_slug → list of InputFile sorted by
    sequence_number.
    """
    groups: dict[str, list[InputFile]] = {}
    for inp in inputs:
        if inp.input_type == "series" and inp.series_slug:
            groups.setdefault(inp.series_slug, []).append(inp)

    # Sort each group by sequence_number
    for slug in groups:
        groups[slug].sort(key=lambda x: x.sequence_number)

    return groups
