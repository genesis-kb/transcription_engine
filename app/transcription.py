import glob
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import yt_dlp

from app import __version__, application, services, utils
from app.config import settings
from app.data_fetcher import DataFetcher
from app.data_writer import DataWriter
from app.exceptions import DuplicateSourceError
from app.exporters import ExporterFactory, TranscriptExporter
from app.github_api_handler import GitHubAPIHandler
from app.logging import get_logger
from app.services.correction import CorrectionService
from app.services.database_service import get_database_service
from app.services.global_tag_manager import GlobalTagManager
from app.services.metadata_extractor import MetadataExtractorService
from app.services.summarizer import SummarizerService

# from app.metadata_parser import MetadataParser
from app.transcript import RSS, Audio, Playlist, Source, Transcript, Video, _yt_opts


class Transcription:
    def __init__(
        self,
        model="tiny",
        github=False,
        summarize=False,
        deepgram=False,
        smallestai=False,
        diarize=False,
        upload=False,
        model_output_dir="transcripts/",
        nocleanup=False,
        json=False,
        markdown=False,
        text_output=False,
        username=None,
        test_mode=False,
        working_dir=None,
        batch_preprocessing_output=False,
        needs_review=False,
        include_metadata=True,
        correct=False,
        llm_provider=settings.LLM_PROVIDER,
        llm_correction_model=settings.config.get("llm_correction_model", "gpt-4o"),
        llm_summary_model=settings.config.get("llm_summary_model", "gpt-4o"),
        no_db=False,
    ):
        # Pipeline robustness settings
        self.max_retries = int(
            settings.config.get("pipeline_max_retries", 3)
        )
        self.retry_delay = int(
            settings.config.get("pipeline_retry_delay_seconds", 10)
        )
        self._correct_enabled = correct
        self._summarize_enabled = summarize
        self.nocleanup = nocleanup
        self.status = "idle"
        self.test_mode = test_mode
        self.no_db = no_db
        self.logger = get_logger()
        self.tmp_dir = (
            working_dir if working_dir is not None else tempfile.mkdtemp()
        )

        self.transcript_by = self.__configure_username(username)
        self.markdown = markdown or test_mode
        self.include_metadata = include_metadata

        self.metadata_writer = DataWriter(
            self.__configure_tstbtc_metadata_dir()
        )

        # Initialize global tag manager
        self.tag_manager = GlobalTagManager(
            self.__configure_tstbtc_metadata_dir()
        )

        self.exporters: dict[str, TranscriptExporter] = (
            ExporterFactory.create_exporters(
                config={
                    "markdown": self.markdown,
                    "text_output": text_output,
                    "json": json,
                    "model_output_dir": model_output_dir,
                },
                transcript_by=self.transcript_by,
            )
        )

        self.model_output_dir = model_output_dir
        self.github = github
        self.github_handler = None
        if self.github:
            self.github_handler = GitHubAPIHandler()
        self.review_flag = self.__configure_review_flag(needs_review)

        # Named service attributes — each maps to one pipeline stage.
        # Storing them separately (instead of a flat processing_services list)
        # means _build_pipeline_stages() can reference them by name, making
        # it trivial to add/reorder/disable individual stages later.
        self.metadata_extractor = (
            MetadataExtractorService() if not test_mode else None
        )
        self.correction_service = (
            CorrectionService(provider=llm_provider, model=llm_correction_model)
            if correct
            else None
        )
        self.summary_service = (
            SummarizerService(provider=llm_provider, model=llm_summary_model)
            if summarize
            else None
        )

        # Keep processing_services for backward-compatibility with postprocess()
        self.processing_services = list(
            filter(
                None,
                [
                    self.metadata_extractor,
                    self.correction_service,
                    self.summary_service,
                ],
            )
        )

        if deepgram:
            self.service = services.Deepgram(
                summarize, diarize, upload, self.metadata_writer
            )
        elif smallestai:
            self.service = services.SmallestAI(
                diarize, upload, self.metadata_writer
            )
        else:
            self.service = services.Whisper(model, upload, self.metadata_writer)

        self.transcripts: list[Transcript] = []
        self.existing_media = None
        self.preprocessing_output = [] if batch_preprocessing_output else None
        self.data_fetcher = DataFetcher(base_url="http://btctranscripts.com")

        self.logger.debug(f"Temp directory: {self.tmp_dir}")

    def _create_subdirectory(self, subdir_name):
        """Helper method to create subdirectories within the central temp director"""
        subdir_path = os.path.join(self.tmp_dir, subdir_name)
        os.makedirs(subdir_path)
        return subdir_path

    def __configure_tstbtc_metadata_dir(self):
        metadata_dir = settings.TSTBTC_METADATA_DIR
        if not metadata_dir:
            alternative_metadata_dir = "metadata/"
            self.logger.debug(
                f"'TSTBTC_METADATA_DIR' environment variable is not defined. Metadata will be stored at '{alternative_metadata_dir}'."
            )
            return alternative_metadata_dir
        return metadata_dir

    def __configure_review_flag(self, needs_review):
        # sanity check
        if needs_review and not self.markdown:
            raise Exception(
                "The `--needs-review` flag is only applicable when creating a markdown"
            )

        if needs_review or self.github_handler:
            return " --needs-review"
        else:
            return ""

    def _find_cached_metadata(self, source_file: str, loc: str) -> Optional[dict]:
        """Scan the local metadata folder for an existing file whose source_file
        matches the given URL.  Returns the parsed JSON dict, or None if not found.

        This lets add_transcription_source() skip the yt_dlp metadata fetch
        entirely when we already have the video info on disk.
        """
        folder = os.path.join(self.metadata_writer.base_dir, loc)
        for filepath in glob.glob(os.path.join(folder, "*", "metadata_*.json")):
            try:
                with open(filepath) as fh:
                    data = json.load(fh)
                if data.get("source_file") == source_file or data.get("media") == source_file:
                    self.logger.info(
                        f"Cache hit for '{source_file}' — loading metadata from disk, skipping yt_dlp."
                    )
                    return data
            except Exception:
                continue
        return None

    def __configure_username(self, username: str | None):
        if self.test_mode:
            return "username"
        if username:
            return username
        else:
            raise Exception(
                "You need to provide a username for transcription attribution"
            )

    def _initialize_source(self, source: Source, youtube_metadata, chapters):
        """Initialize transcription source based on metadata
        Returns the initialized source (Audio, Video, Playlist)"""

        def check_if_youtube(source: Source):
            """Helper method to check and assign a valid source for
            a YouTube playlist or YouTube video by requesting its metadata
            Does not support video-ids, only urls"""
            try:
                ydl_opts = _yt_opts(
                    quiet=False,
                    extract_flat=True,
                )
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(
                        source.source_file, download=False
                    )
                    if "entries" in info_dict:
                        # Playlist URL, not a single video
                        # source.title = info_dict["title"]
                        return Playlist(
                            source=source, entries=info_dict["entries"]
                        )
                    elif "title" in info_dict:
                        # Single video URL
                        return Video(source=source)
                    else:
                        raise Exception(source.source_file)

            except Exception as e:
                # Invalid URL or video not found
                raise Exception(f"Invalid source: {e}")

        try:
            if source.source_file.lower().endswith(
                (".mp3", ".wav", ".m4a", ".aac")
            ):
                return Audio(source=source, chapters=chapters)
            if source.source_file.endswith(("rss", ".xml")):
                return RSS(source=source)

            if youtube_metadata is not None:
                # we have youtube metadata, this can only be true for videos
                source.preprocess = False
                return Video(
                    source=source,
                    youtube_metadata=youtube_metadata,
                    chapters=chapters,
                )
            if source.source_file.lower().endswith((".mp4", ".webm", ".mov")):
                # regular remote video, not youtube
                source.preprocess = False
                return Video(source=source)
            youtube_source = check_if_youtube(source)
            if youtube_source == "unknown":
                raise Exception(f"Invalid source: {source}")
            return youtube_source
        except Exception as e:
            raise Exception(f"Error from assigning source: {e}")

    def _new_transcript_from_source(self, source: Source):
        """Helper method to initialize a new Transcript from source"""
        metadata_file = None
        if source.preprocess:
            # At this point of the process, we have all the metadata for the source
            # parser = MetadataParser()
            # source = parser.parse(source)
            if self.preprocessing_output is None:
                # Save preprocessing output for the specific source
                metadata_file = self.metadata_writer.write_json(
                    data=source.to_json(),
                    file_path=source.output_path_with_title,
                    filename="metadata",
                )
            else:
                # Keep preprocessing outputs for later use
                self.preprocessing_output.append(source.to_json())
        # Initialize new transcript from source
        transcript = Transcript(
            source=source,
            test_mode=self.test_mode,
            metadata_file=metadata_file,
        )

        # Update global tag dictionary with new transcript metadata
        try:
            self.tag_manager.update_from_transcript(transcript)
            self.logger.debug(
                f"Updated global tag dictionary with transcript: {source.title}"
            )
        except Exception as e:
            self.logger.warning(f"Failed to update global tag dictionary: {e}")

        self.transcripts.append(transcript)

    def add_transcription_source(
        self,
        source_file,
        loc="misc",
        title=None,
        date=None,
        summary=None,
        episode=None,
        additional_resources=None,
        # cutoff_date serves as a threshold, and only content published beyond this point is relevant
        cutoff_date=None,
        tags=None,
        category=None,
        speakers=None,
        preprocess=True,
        youtube_metadata=None,
        link=None,
        chapters=None,
        nocheck=False,
        excluded_media=None,
    ):
        """Add a source for transcription"""
        if excluded_media is None:
            excluded_media = []
        if chapters is None:
            chapters = []
        if speakers is None:
            speakers = []
        if category is None:
            category = []
        if tags is None:
            tags = []
        if additional_resources is None:
            additional_resources = []
        if cutoff_date:
            cutoff_date = utils.validate_and_parse_date(cutoff_date)
            # Even with a cutoff date, for YouTube playlists we still need to download the metadata
            # for each video in order to obtain the `upload_date` and use it for filtering
            self.logger.debug(
                f"A cutoff date of '{cutoff_date}' is given. Processing sources published after this date."
            )
        preprocess = False if self.test_mode else preprocess
        transcription_sources = {"added": [], "exist": []}
        # check if source is a local file
        local = False
        if os.path.isfile(source_file):
            local = True
        if (
            not nocheck
            and not local
            and self.existing_media is None
            and not self.test_mode
        ):
            self.existing_media = self.data_fetcher.get_existing_media()
        # combine existing media from btctranscripts.com with excluded media given from source
        excluded_media = {value: True for value in excluded_media}
        if self.existing_media is not None:
            excluded_media.update(self.existing_media)
        # initialize source
        # TODO: find a better way to pass metadata into the source
        # as it is, every new metadata field needs to be passed to `Source`
        # I can assign directly after initialization like I do with `additional_resources`
        # but I'm not sure if it's the best way to do it.
        # Check if we already have metadata for this URL on disk.
        # If so, inject it directly and skip the yt_dlp network call.
        if youtube_metadata is None and not local:
            cached = self._find_cached_metadata(source_file, loc)
            if cached:
                title = title or cached.get("title", title)
                date = date or cached.get("date", date)
                tags = tags or cached.get("tags", tags) or []
                category = category or cached.get("categories", category) or []
                speakers = speakers or cached.get("speakers", speakers) or []
                chapters = chapters or cached.get("chapters", chapters) or []
                youtube_metadata = cached.get("youtube", {})
                summary = summary or cached.get("description", summary)

        source = self._initialize_source(
            source=Source(
                source_file=source_file,
                loc=loc,
                local=local,
                title=title,
                date=date,
                summary=summary,
                episode=episode,
                tags=tags,
                category=category,
                speakers=speakers,
                preprocess=preprocess,
                link=link,
            ),
            youtube_metadata=youtube_metadata,
            chapters=chapters,
        )
        source.additional_resources = additional_resources
        self.logger.debug(f"Detected source: {source}")

        # Check if source is already in the transcription queue
        for transcript in self.transcripts:
            if (
                transcript.source.loc == loc
                and transcript.source.title == title
            ):
                self.logger.warning(f"Source already exists in queue: {title}")
                raise DuplicateSourceError(loc, title)

        if source.type == "playlist":
            # add a transcript for each source/video in the playlist
            for video in source.videos:
                is_eligible = video.date > cutoff_date if cutoff_date else True
                if video.media not in excluded_media and is_eligible:
                    transcription_sources["added"].append(video.source_file)
                    self._new_transcript_from_source(video)
                else:
                    transcription_sources["exist"].append(video.source_file)
        elif source.type == "rss":
            # add a transcript for each source/audio in the rss feed
            for entry in source.entries:
                is_eligible = entry.date > cutoff_date if cutoff_date else True
                if entry.media not in excluded_media and is_eligible:
                    transcription_sources["added"].append(entry.source_file)
                    self._new_transcript_from_source(entry)
                else:
                    transcription_sources["exist"].append(entry.source_file)
        elif source.type in ["audio", "video"]:
            if source.media not in excluded_media:
                transcription_sources["added"].append(source.source_file)
                self._new_transcript_from_source(source)
                self.logger.info(
                    f"Source added for transcription: {source.title}"
                )
            else:
                transcription_sources["exist"].append(source.source_file)
                self.logger.info(
                    f"Source already exists ({self.data_fetcher.base_url}): {source.title}"
                )
        else:
            raise Exception(f"Invalid source: {source_file}")
        if source.type in ["playlist", "rss"]:
            self.logger.info(
                f"{source.title}: sources added for transcription: {len(transcription_sources['added'])} (Ignored: {len(transcription_sources['exist'])} sources)"
            )
        return transcription_sources

    def add_transcription_source_JSON(self, json_file, nocheck=False):
        # validation checks
        utils.check_if_valid_file_path(json_file)
        sources = utils.check_if_valid_json(json_file)

        # Check if JSON contains multiple sources
        if not isinstance(sources, list):
            # Initialize an array with 'sources' as the only element
            sources = [sources]

        self.logger.debug(f"Adding transcripts from {json_file}")
        for source in sources:
            metadata = utils.configure_metadata_given_from_JSON(source)

            self.add_transcription_source(
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
                excluded_media=metadata["excluded_media"],
                nocheck=nocheck,
                cutoff_date=metadata["cutoff_date"],
            )

    def remove_transcription_source_JSON(self, json_file):
        # Validate and parse the JSON file
        utils.check_if_valid_file_path(json_file)
        sources = utils.check_if_valid_json(json_file)

        # Check if JSON contains multiple sources
        if not isinstance(sources, list):
            sources = [sources]

        self.logger.debug(f"Removing transcripts from {json_file}")
        removed_sources = []

        for source in sources:
            metadata = utils.configure_metadata_given_from_JSON(source)
            loc = metadata["loc"]
            title = metadata["title"]

            for transcript in self.transcripts:
                if (
                    transcript.source.loc == loc
                    and transcript.source.title == title
                ):
                    self.transcripts.remove(transcript)
                    removed_sources.append(transcript)
                    self.logger.info(f"Removed source from queue: {title}")
                    break
            else:
                self.logger.warning(f"Source not found in queue: {title}")

        return removed_sources

    def start(self, test_transcript=None):
        """Process every transcript in the queue.

        A single video failure never aborts the entire batch — each video is
        handled by _run_pipeline() which catches its own exceptions.
        """
        self.status = "in_progress"
        for transcript in self.transcripts:
            transcript.status = "in_progress"
            self.logger.info(
                f"Starting pipeline for: {transcript.source.source_file}"
            )
            self._run_pipeline(transcript, test_transcript)

        self.status = "completed"
        completed = [
            t for t in self.transcripts if t.status == "completed"
        ]
        if self.github and completed:
            self.push_to_github(completed)
        return self.transcripts

    def _run_pipeline(self, transcript: Transcript, test_transcript=None) -> None:
        """Run all pipeline stages for a single transcript.

        Stages are expressed as plain (name, fn, enabled) tuples so that
        adding a new one (e.g. translation) is just appending a tuple here.

        Behaviour:
        - Loads any existing pipeline state from metadata/ (resumability).
        - Skips stages already completed in a previous run.
        - On stage failure, retries up to max_retries times with backoff.
        - After exhausting retries, marks remaining stages 'skipped',
          sets overall='failed', and returns — the next video is unaffected.
        - Export (markdown) is the last stage; it is naturally skipped if
          any earlier stage failed.
        """
        def do_media(t: Transcript) -> None:
            t.tmp_dir = self._create_subdirectory(
                f"transcript-{utils.slugify(t.title)}"
            )
            t.process_source(t.tmp_dir)

        def do_transcription(t: Transcript) -> None:
            if self.test_mode:
                t.outputs["raw"] = test_transcript or "test-mode"
            else:
                self.service.transcribe(t)
                if self.metadata_extractor:
                    self.metadata_extractor.process(t)

        def do_correction(t: Transcript) -> None:
            self.correction_service.process(t)

        def do_summarization(t: Transcript) -> None:
            self.summary_service.process(t)

        def do_export(t: Transcript) -> None:
            self.export(t)

        # Each tuple: (stage_name, fn, enabled)
        # To add a new stage, just append a tuple here.
        stages: list[tuple[str, Callable, bool]] = [
            ("media_processing", do_media,        True),
            ("transcription",    do_transcription, True),
            ("correction",       do_correction,    self._correct_enabled),
            ("summarization",    do_summarization, self._summarize_enabled),
            ("export",           do_export,        True),
        ]

        # Load any state persisted from a previous run FIRST so that saved
        # "completed" stages are not overwritten by the pending initialisation below.
        self._load_existing_pipeline_state(transcript)

        # If transcription was already completed in a previous run, load the
        # raw transcript text from disk so downstream stages (correction,
        # summarization) have actual content to work with.
        transcription_done = (
            transcript.pipeline_state["stages"]
            .get("transcription", {})
            .get("status") == "completed"
        )
        if transcription_done:
            self._load_raw_transcript_from_disk(transcript)

        # initialise any stages not already in the loaded state as pending.
        for name, _, _ in stages:
            transcript.pipeline_state["stages"].setdefault(name, {"status": "pending"})

        transcript.pipeline_state["overall"] = "in_progress"
        self._persist_pipeline_state(transcript)

        for i, (name, fn, enabled) in enumerate(stages):
            current_status = (
                transcript.pipeline_state["stages"]
                .get(name, {})
                .get("status", "pending")
            )

            if current_status == "completed":
                self.logger.info(
                    f"[PIPELINE] [{transcript.title}] [{name}] → skipped (already completed)"
                )
                continue

            if not enabled:
                self._mark_stage(transcript, name, "skipped")
                self.logger.info(
                    f"[PIPELINE] [{transcript.title}] [{name}] → skipped (disabled)"
                )
                continue

            success = self._run_stage_with_retry(name, fn, transcript)

            if not success:
                for remaining_name, _, _ in stages[i + 1:]:
                    self._mark_stage(transcript, remaining_name, "skipped")
                transcript.pipeline_state["overall"] = "failed"
                transcript.pipeline_state["failed_at"] = name
                self._persist_pipeline_state(transcript)
                transcript.status = "failed"
                self.logger.error(
                    f"[{transcript.title}] Pipeline failed at '{name}'. "
                    "Remaining stages skipped."
                )
                return

        transcript.pipeline_state["overall"] = "completed"
        self._persist_pipeline_state(transcript)
        transcript.status = "completed"
        self.logger.info(f"[PIPELINE] [{transcript.title}] → pipeline completed successfully")

    def _run_stage_with_retry(
        self,
        stage_name: str,
        fn: Callable[[Transcript], None],
        transcript: Transcript,
    ) -> bool:
        """Execute a stage function with exponential-backoff retry.

        Returns True on success, False after exhausting all retries.
        """
        self._mark_stage(transcript, stage_name, "in_progress")
        self.logger.info(f"[PIPELINE] [{transcript.title}] [{stage_name}] → in_progress")

        for attempt in range(1, self.max_retries + 1):
            try:
                fn(transcript)
                self._update_stage_state(
                    transcript, stage_name, "completed", attempts=attempt
                )
                self.logger.info(
                    f"[PIPELINE] [{transcript.title}] [{stage_name}] → completed (attempt {attempt})"
                )
                return True
            except Exception as exc:
                if attempt == self.max_retries:
                    self.logger.error(
                        f"[PIPELINE] [{transcript.title}] [{stage_name}] → failed after "
                        f"{attempt} attempt(s): {exc}"
                    )
                    self._update_stage_state(
                        transcript, stage_name, "failed",
                        error=str(exc), attempts=attempt,
                    )
                    return False
                wait = self.retry_delay * attempt
                self.logger.warning(
                    f"[PIPELINE] [{transcript.title}] [{stage_name}] → attempt {attempt} failed "
                    f"— retrying in {wait}s. Reason: {exc}"
                )
                time.sleep(wait)
        return False

    # ------------------------------------------------------------------
    # Pipeline state helpers
    # ------------------------------------------------------------------

    def _mark_stage(self, transcript: Transcript, stage_name: str, status: str) -> None:
        """Set a stage to a terminal/transitional status without extra metadata."""
        transcript.pipeline_state["stages"][stage_name] = {"status": status}
        self._persist_pipeline_state(transcript)

    def _update_stage_state(
        self,
        transcript: Transcript,
        stage_name: str,
        status: str,
        error: Optional[str] = None,
        attempts: Optional[int] = None,
    ) -> None:
        """Write rich stage metadata (timestamps, error, attempts)."""
        entry: dict = {"status": status}
        if status == "completed":
            entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        if error:
            entry["error"] = error
        if attempts is not None:
            entry["attempts"] = attempts
        transcript.pipeline_state["stages"][stage_name] = entry
        self._persist_pipeline_state(transcript)

    def _persist_pipeline_state(self, transcript: Transcript) -> None:
        """Upsert the pipeline_state block at the top of the metadata JSON.

        If no metadata file exists yet (e.g. media_processing failed before
        anything was written), a minimal stub is created so the failure is
        always recorded on disk.
        """
        folder = os.path.join(
            self.metadata_writer.base_dir,
            transcript.source.output_path_with_title,
        )
        os.makedirs(folder, exist_ok=True)

        existing_files = sorted(glob.glob(os.path.join(folder, "metadata_*.json")))

        if existing_files:
            filepath = existing_files[-1]
            try:
                with open(filepath) as fh:
                    existing_data = json.load(fh)
            except Exception:
                existing_data = {}
        else:
            # No metadata file yet — create a stub so the failure is visible.
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
            filepath = os.path.join(folder, f"metadata_{ts}.json")
            existing_data = {
                "title": transcript.title,
                "source_file": transcript.source.source_file,
            }

        # pipeline_state always goes first for visibility
        updated = {
            "pipeline_state": transcript.pipeline_state,
            **{k: v for k, v in existing_data.items() if k != "pipeline_state"},
        }

        with open(filepath, "w") as fh:
            json.dump(updated, fh, indent=4)

    def _load_existing_pipeline_state(self, transcript: Transcript) -> None:
        """Load a previously persisted pipeline_state into the transcript.

        This enables resumability: if the same URL is re-queued after a
        partial failure, the pipeline skips all already-completed stages.
        """
        folder = os.path.join(
            self.metadata_writer.base_dir,
            transcript.source.output_path_with_title,
        )
        existing_files = sorted(glob.glob(os.path.join(folder, "metadata_*.json")))
        if not existing_files:
            return

        # Scan ALL metadata files newest-first for one that has a pipeline_state.
        # This is necessary because add_to_queue() writes a brand-new metadata file
        # (without pipeline_state) BEFORE start() is called, so the "latest" file
        # is often a fresh blank one — not the persisted state from a previous run.
        saved = None
        for filepath in reversed(existing_files):
            try:
                with open(filepath) as fh:
                    data = json.load(fh)
                if "pipeline_state" in data:
                    saved = data["pipeline_state"]
                    break
            except Exception:
                continue

        if saved is None:
            return

        # Merge saved stages into the transcript's current (all-pending) state
        for stage_name, stage_data in saved.get("stages", {}).items():
            transcript.pipeline_state["stages"].setdefault(stage_name, stage_data)

        if saved.get("failed_at"):
            transcript.pipeline_state["failed_at"] = saved["failed_at"]

        self.logger.info(
            f"[PIPELINE] [{transcript.title}] Loaded existing state "
            f"(overall={saved.get('overall', 'unknown')})."
        )

    def _load_raw_transcript_from_disk(self, transcript: Transcript) -> None:
        """Populate transcript.outputs['raw'] from the saved smallestai JSON.

        Called when the transcription stage is already 'completed' in the
        pipeline state (resumability path).  Without this, correction and
        summarization would receive None as input.
        """
        folder = os.path.join(
            self.metadata_writer.base_dir,
            transcript.source.output_path_with_title,
        )
        stt_files = sorted(glob.glob(os.path.join(folder, "smallestai_*.json")))
        if not stt_files:
            self.logger.warning(
                f"[{transcript.title}] Transcription marked complete but no "
                "smallestai_*.json found — raw transcript will be empty."
            )
            return

        try:
            transcript.outputs["transcription_service_output_file"] = stt_files[-1]
            # Reuse SmallestAI's own finalizer to reconstruct the raw text
            self.service.finalize_transcript(transcript)
            self.logger.info(
                f"[{transcript.title}] Loaded raw transcript from disk "
                f"({os.path.basename(stt_files[-1])})."
            )
        except Exception as exc:
            self.logger.warning(
                f"[{transcript.title}] Could not load raw transcript from disk: {exc}"
            )

    def push_to_github(self, transcripts: list[Transcript]):
        if not self.github_handler:
            return

        markdown_exporter = self.exporters.get("markdown")
        if not markdown_exporter:
            self.logger.error(
                "Markdown exporter not configured, cannot push to GitHub."
            )
            return

        pr_url_transcripts = self.github_handler.push_transcripts(
            transcripts, markdown_exporter
        )
        if pr_url_transcripts:
            self.logger.info(
                f"transcripts: Pull request created: {pr_url_transcripts}"
            )
            pr_url_metadata = self.github_handler.push_metadata(
                transcripts, pr_url_transcripts
            )
            if pr_url_metadata:
                self.logger.info(
                    f"metadata: Pull request created: {pr_url_metadata}"
                )
            else:
                self.logger.error("metadata: Failed to create pull request.")
        else:
            self.logger.error("transcripts: Failed to create pull request.")

    def write_to_markdown_file(self, transcript: Transcript):
        """
        Legacy method that uses the markdown exporter to write a markdown file.
        This maintains compatibility with existing code while using the new architecture.
        """
        self.logger.debug(
            "Creating markdown file with transcription (using exporter)..."
        )

        try:
            if "markdown" not in self.exporters:
                raise Exception("Markdown exporter not configured")

            markdown_exporter = self.exporters["markdown"]
            export_kwargs = {
                "version": __version__,
                "review_flag": self.review_flag,
                "add_timestamp": False,
                "include_metadata": self.include_metadata,
            }

            markdown_file = markdown_exporter.export(
                transcript, **export_kwargs
            )
            self.logger.info(f"Markdown file stored at: {markdown_file}")
            return markdown_file

        except Exception as e:
            raise Exception(f"Error writing to markdown file: {e}")

    def postprocess(self, transcript: Transcript) -> None:
        for service in self.processing_services:
            service.process(transcript)

    def export(self, transcript: Transcript):
        """Exports the transcript to the configured formats."""
        text_exporter = self.exporters.get("text")
        if text_exporter:
            # Save raw, corrected, and summary files
            if transcript.outputs.get("raw"):
                text_exporter.export(
                    transcript,
                    add_timestamp=False,
                    content_key="raw",
                    suffix="_raw",
                )
            if transcript.outputs.get("corrected_text"):
                text_exporter.export(
                    transcript,
                    add_timestamp=False,
                    content_key="corrected_text",
                    suffix="_corrected",
                )
            if transcript.summary:
                text_exporter.export(
                    transcript,
                    add_timestamp=False,
                    content_key="summary",
                    suffix="_summary",
                )

        if self.markdown or self.github_handler:
            transcript.outputs["markdown"] = self.write_to_markdown_file(
                transcript,
            )

        if "json" in self.exporters:
            transcript.outputs["json"] = self.exporters["json"].export(
                transcript
            )

        # Save to database if configured (skip when --no-db is set)
        if self.no_db:
            self.logger.info("Skipping database save (--no-db flag set)")
        else:
            db = get_database_service()
            if db.is_available:
                db.save_from_transcript_object(transcript)

    def clean_up(self):
        self.logger.debug("Cleaning up...")
        application.clean_up(self.tmp_dir)

    def __del__(self):
        if self.nocleanup:
            self.logger.info("Not cleaning up temp files...")
        else:
            self.clean_up()

    def __str__(self):
        excluded_fields = ["logger", "existing_media"]
        fields = {
            key: value
            for key, value in self.__dict__.items()
            if key not in excluded_fields
        }
        return f"Transcription:{str(fields)}"
