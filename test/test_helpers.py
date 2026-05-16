import yaml

from app import __version__


def check_md_file(
    path,
    transcript_by,
    media,
    title=None,
    date=None,
    tags=None,
    categories=None,
    speakers=None,
    local=False,
    chapters=None,
):
    """
    Check if the markdown file at the given path contains the expected metadata and content.

    :param path: Path to the markdown file
    :param transcript_by: Expected transcriber
    :param media: Expected media link
    :param title: Expected title
    :param date: Expected date
    :param tags: Expected tags (list)
    :param category: Expected category (list)
    :param speakers: Expected speakers (list)
    :param local: Whether the media is local
    :param chapters: Expected chapters (list)
    :return: True if all checks pass, raises AssertionError otherwise
    """
    if speakers is None:
        speakers = []
    if categories is None:
        categories = []
    if tags is None:
        tags = []
    if not path:
        raise ValueError("No path provided")

    with open(path) as file:
        contents = file.read()

    # Split the content into metadata and body
    parts = contents.split("---\n")
    if len(parts) < 3:
        raise ValueError("Invalid markdown format: missing YAML front matter")

    yaml_content = parts[1].strip()
    body = parts[2].strip()

    # Parse YAML content
    fields = yaml.safe_load(yaml_content)

    # Check fields
    assert (
        fields["transcript_by"]
        == f"{transcript_by} via tstbtc v{__version__}"
    ), "Incorrect transcript_by field"

    if not local:
        assert fields.get("media") == media

    assert fields.get("title") == title

    if date:
        assert fields.get("date") == date

    if tags:
        assert set(fields.get("tags", [])) == set(tags)

    if speakers:
        assert set(fields.get("speakers", [])) == set(speakers)

    if categories:
        assert set(fields.get("categories", [])) == set(categories)

    # Check chapters
    if chapters:
        detected_chapters = [
            x[3:].strip() for x in body.split("\n") if x.startswith("##")
        ]
        assert detected_chapters == chapters

    return True
