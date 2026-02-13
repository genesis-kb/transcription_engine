import json
import logging
import traceback
import os
import click

from app import __app_name__, __version__, commands, utils
from app.api_client import APIClient
from app.commands.cli_utils import (
    get_transcription_url, 
    auto_start_server
)
from app.config import settings
from app.data_writer import DataWriter
from app.logging import configure_logger, get_logger
from app.transcription import Transcription

logger = get_logger()


def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"{__app_name__} v{__version__}")
    ctx.exit()


@click.option(
    "-v",
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="Show the application's version and exit.",
)
@click.option(
    "--auto-server",
    is_flag=True,
    default=settings.config.getboolean("auto_server", True),
    help="Automatically start the server if it's not running (default: True)",
    show_default=True,
)
@click.option(
    "--server-mode",
    type=click.Choice(["dev", "prod"]),
    default=settings.config.get("server_mode", "prod"),
    help="Mode to use when automatically starting the server",
    show_default=True,
)
@click.option(
    "--server-verbose",
    is_flag=True,
    default=settings.config.getboolean("server_verbose", False),
    help="Show server output directly in the console when auto-starting",
    show_default=True,
)
@click.group()
@click.pass_context
def cli(ctx, auto_server, server_mode, server_verbose):
    # Store auto_server and server_mode in the context for use in ServerCheckGroup
    ctx.obj = {
        "auto_server": auto_server,
        "server_mode": server_mode,
        "server_verbose": server_verbose
    }
    pass


def print_help(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    logging.info(ctx.get_help())
    ctx.exit()


whisper = click.option(
    "-m",
    "--model",
    type=click.Choice(
        [
            "tiny",
            "tiny.en",
            "base",
            "base.en",
            "small",
            "small.en",
            "medium",
            "medium.en",
            "large-v2",
        ]
    ),
    default=settings.config.get("model", "tiny.en"),
    show_default=True,
    help="Select which whisper model to use for the transcription",
)
deepgram = click.option(
    "-D",
    "--deepgram",
    is_flag=True,
    default=settings.config.getboolean("deepgram", False),
    show_default=True,
    help="Use deepgram for transcription",
)
diarize = click.option(
    "-M",
    "--diarize",
    is_flag=True,
    default=settings.config.getboolean("diarize", False),
    show_default=True,
    help="Supply this flag if you have multiple speakers AKA "
    "want to diarize the content",
)
summarize = click.option(
    "-S",
    "--summarize",
    is_flag=True,
    default=settings.config.getboolean("summarize", False),
    show_default=True,
    help="Summarize the transcript using the configured LLM provider.",
)
cutoff_date = click.option(
    "--cutoff-date",
    type=str,
    default=settings.config.get("cutoff_date", None),
    help=(
        "Specify a cutoff date (in YYYY-MM-DD format) to process only sources "
        "published after this date. Sources with a publication date on or before "
        "the cutoff will be excluded from processing. This option is useful for "
        "focusing on newer content or limiting the scope of processing to a "
        "specific date range."
    ),
)
nocheck = click.option(
    "--nocheck",
    is_flag=True,
    default=settings.config.getboolean("nocheck", False),
    show_default=True,
    help=f"Do not check for existing sources using {settings.BTC_TRANSCRIPTS_URL}/status.json",
)
username = click.option(
    "--username",
    type=str,
    default=settings.config.get("username", None),
    help=("Specify a username for transcription attribution."),
)
github = click.option(
    "--github",
    is_flag=True,
    default=settings.config.getboolean("github", False),
    help="Push the resulting transcript(s) to GitHub",
    show_default=True,
)
upload_to_s3 = click.option(
    "-u",
    "--upload",
    is_flag=True,
    default=settings.config.getboolean("upload_to_s3", False),
    help="Upload processed model files to AWS S3",
)
save_to_markdown = click.option(
    "--markdown",
    is_flag=True,
    default=settings.config.getboolean("save_to_markdown", False),
    help="Save the resulting transcript to a markdown format",
)
save_to_text = click.option(
    "--text",
    is_flag=True,
    default=settings.config.getboolean("save_to_text", False),
    help="Save the resulting transcript to a plain text file",
)
markdown_no_metadata = click.option(
    "--no-metadata",
    is_flag=True,
    default=settings.config.getboolean("no_metadata", False),
    help="Don't include metadata in the markdown output",
)
save_to_json = click.option(
    "--json",
    is_flag=True,
    default=settings.config.getboolean("save_to_json", False),
    help="Save the resulting transcript to a JSON format",
)
needs_review = click.option(
    "--needs-review",
    is_flag=True,
    default=settings.config.getboolean("needs_review", False),
    help="Add 'needs review' flag to the resulting transcript",
)
model_output_dir = click.option(
    "-o",
    "--model_output_dir",
    type=str,
    default=settings.config.get("model_output_dir", "local_models/"),
    show_default=True,
    help="Set the directory for saving model outputs",
)
nocleanup = click.option(
    "--nocleanup",
    is_flag=True,
    default=settings.config.getboolean("nocleanup", False),
    help="Do not remove temp files on exit",
)
verbose_logging = click.option(
    "-V",
    "--verbose",
    is_flag=True,
    default=settings.config.getboolean("verbose_logging", False),
    help="Supply this flag to enable verbose logging",
)

correct_transcript = click.option(
    "--correct",
    is_flag=True,
    default=settings.config.getboolean("correct", False),
    help="Correct the transcript using the configured LLM provider.",
)
llm_provider = click.option(
    "--llm-provider",
    type=click.Choice(["openai", "google", "claude"]),
    default=settings.config.get("llm_provider", "openai"),
    help="LLM provider for correction and summarization.",
)

add_loc = click.option(
    "--loc",
    default="misc",
    help="Add the location in the bitcointranscripts hierarchy that you want to associate the transcript with",
)
add_title = click.option(
    "-t",
    "--title",
    type=str,
    help="Add the title for the resulting transcript (required for audio files)",
)
add_date = click.option(
    "-d",
    "--date",
    type=str,
    help="Add the event date to transcript's metadata in format 'yyyy-mm-dd'",
)
add_tags = click.option(
    "-T",
    "--tags",
    multiple=True,
    help="Add a tag to transcript's metadata (can be used multiple times)",
)
add_speakers = click.option(
    "-s",
    "--speakers",
    multiple=True,
    help="Add a speaker to the transcript's metadata (can be used multiple times)",
)
add_category = click.option(
    "-c",
    "--category",
    multiple=True,
    help="Add a category to the transcript's metadata (can be used multiple times)",
)


@cli.command()
@click.argument("source", nargs=1)
# Available transcription models and services
@whisper
@deepgram
# Available features for transcription services
@diarize
@summarize
# Options for adding metadata
@add_title
@add_date
@add_tags
@add_speakers
@add_category
@add_loc
# Options for configuring the transcription preprocess
@cutoff_date
@nocheck
# Options for configuring the transcription postprocess
@username
@github
@upload_to_s3
@save_to_markdown
@save_to_text
@markdown_no_metadata
@save_to_json
@needs_review
# Configuration options
@model_output_dir
@nocleanup
@verbose_logging
@auto_start_server
@correct_transcript
@llm_provider
def transcribe(
    source: str,
    loc: str,
    model: str,
    title: str,
    date: str,
    tags: list,
    speakers: list,
    category: list,
    username: str,
    github: bool,
    deepgram: bool,
    summarize: bool,
    diarize: bool,
    upload: bool,
    verbose: bool,
    model_output_dir: str,
    nocleanup: bool,
    json: bool,
    markdown: bool,
    text: bool,
    no_metadata: bool,
    needs_review: bool,
    cutoff_date: str,
    correct: bool,
    llm_provider: str,
    nocheck: bool,
) -> None:
    """Transcribe the provided sources. Suported sources include: \n
    - YouTube videos and playlists\n
    - Local and remote audio files\n
    - JSON files containing individual sources\n

    Notes:\n
    - The https links need to be wrapped in quotes when running the command
    on zsh\n
    - The JSON can be generated by `preprocess-sources` or created manually
    """
    configure_logger(log_level=logging.INFO)
    url = get_transcription_url()
    api_client = APIClient(url)

    data = {
        "loc": loc,
        "model": model,
        "title": title,
        "date": date,
        "tags": list(tags),
        "speakers": list(speakers),
        "category": list(category),
        "username": username,
        "github": github,
        "deepgram": deepgram,
        "summarize": summarize,
        "diarize": diarize,
        "upload": upload,
        "verbose": verbose,
        "model_output_dir": model_output_dir,
        "nocleanup": nocleanup,
        "json": json,
        "markdown": markdown,
        "text": text,
        "include_metadata": not no_metadata,
        "needs_review": needs_review,
        "cutoff_date": cutoff_date,
        "correct": correct,
        "llm_provider": llm_provider,
        "nocheck": nocheck,
    }
    try:
        queue_response = api_client.add_to_queue(data, source)
        logger.info(queue_response)

        start_response = api_client.start_transcription()
        logger.info(start_response)
    except Exception as e:
        logger.error(f"Transcription operation failed: {e}")


@cli.command()
def get_queue():
    """Get the transcription queue"""
    configure_logger(log_level=logging.INFO)
    url = get_transcription_url()
    api_client = APIClient(url)

    try:
        response = api_client.get_queue()
        logger.info(response)
    except Exception as e:
        logger.error(f"Failed to get queue: {e}")


@cli.command()
@click.argument("source", nargs=1)
# Options for configuring the transcription preprocess
@cutoff_date
@nocheck
# Options for adding metadata
@add_title
@add_date
@add_tags
@add_speakers
@add_category
@add_loc
@auto_start_server
def preprocess(
    source: str,
    loc: str,
    title: str,
    date: str,
    tags: list,
    speakers: list,
    category: list,
    nocheck: bool,
    cutoff_date: str,
):
    """Preprocess the provided sources. Suported sources include: \n
    - YouTube videos and playlists\n
    - JSON files containing individual sources\n

    Preprocessing will fetch all the given sources, and output them
    in a JSON alongside the available metadata.
    The JSON can then be edited and piped to `transcribe`
    """
    configure_logger(log_level=logging.INFO)
    url = get_transcription_url()
    api_client = APIClient(url)

    data = {
        "loc": loc,
        "title": title,
        "date": date,
        "tags": list(tags),
        "speakers": list(speakers),
        "category": list(category),
        "nocheck": nocheck,
        "cutoff_date": cutoff_date,
    }

    try:
        response_data = api_client.preprocess_source(data, source)
        data_writer = DataWriter("local_models/")
        file_path = data_writer.write_json(
            data=response_data.json()["data"],
            file_path="",
            filename="preprocessed_sources",
        )
        logger.info(f"Data successfully written to {file_path}")
    except Exception as e:
        logger.error(f"Preprocessing operation failed: {e}")


@cli.command()
@click.argument(
    "service",
    nargs=1,
    type=click.Choice(
        [
            "whisper",
            "deepgram"
        ]
    )
)
@click.argument("metadata_json_file", nargs=1)
# Options for configuring the transcription postprocess
@username
@github
@upload_to_s3
@save_to_markdown
@save_to_text
@save_to_json
@needs_review
def postprocess(
    metadata_json_file,
    service,
    username: str,
    github: bool,
    upload: bool,
    markdown: bool,
    text: bool,
    json: bool,
    needs_review: bool,
):
    """Postprocess the output of a transcription service.
    Requires the metadata JSON file that is the output of the previous stage
    of the transcription process.
    """
    try:
        configure_logger(log_level=logging.INFO)
        utils.check_if_valid_file_path(metadata_json_file)
        transcription = Transcription(
            deepgram=service == "deepgram",
            github=github,
            upload=upload,
            username=username,
            markdown=markdown,
            text_output=text,
            json=json,
            needs_review=needs_review,
        )
        logger.info(
            f"Postprocessing {service} transcript from {metadata_json_file}")
        with open(metadata_json_file, "r") as outfile:
            metadata_json = json.load(outfile)
        metadata = utils.configure_metadata_given_from_JSON(
            metadata_json, from_json=metadata_json_file)
        transcription.add_transcription_source(
            source_file=metadata["source_file"],
            loc=metadata["loc"],
            title=metadata["title"],
            category=metadata["category"],
            tags=metadata["tags"],
            speakers=metadata["speakers"],
            date=metadata["date"],
            summary=metadata["summary"],
            episode=metadata["episode"],
            additional_resources=metadata["additional_resources"],
            youtube_metadata=metadata["youtube_metadata"],
            chapters=metadata["chapters"],
            link=metadata["media"],
            preprocess=False,
            nocheck=True,
            cutoff_date=metadata["cutoff_date"]
        )
        # Finalize transcription service output
        transcript = transcription.transcripts[0]
        if metadata.get("deepgram_chunks"):
            logger.info("Combining deepgram chunk outputs...")
            all_chunks_output = []
            for chunk_file in metadata["deepgram_chunks"]:
                with open(chunk_file, "r") as chunk:
                    all_chunks_output.append(json.load(chunk))
            overlap_between_chunks = 30.0  # or any other value used during splitting
            transcription_service_output = transcription.service.combine_chunk_outputs(
                all_chunks_output, overlap=overlap_between_chunks)
            transcript.outputs["transcription_service_output_file"] = transcription.service.write_to_json_file(
                transcription_service_output, transcript)
        else:
            transcript.outputs["transcription_service_output_file"] = metadata[f"{service}_output"]

        transcription.service.finalize_transcript(transcript)
        transcription.postprocess(transcript)

        if transcription.github:
            transcription.push_to_github([transcript])
    except Exception as e:
        logger.error(e)
        traceback.print_exc()


cli.add_command(commands.media)
cli.add_command(commands.curator)
cli.add_command(commands.server)

if __name__ == "__main__":
    cli()
