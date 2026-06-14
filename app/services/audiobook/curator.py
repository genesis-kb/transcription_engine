"""Audiobook curation orchestrator.

The curator is the brain of the pipeline. It:
  1. Reads parsed input files (from ingestion.py)
  2. Decides single-article vs. series strategy
  3. Calls the audio pipeline for TTS generation
  4. Persists results via the playlist service

Usage:
    from app.services.audiobook.curator import AudiobookCurator
    curator = AudiobookCurator()
    result = curator.curate_from_directory("input/audiobooks")
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from app.logging import get_logger

from .ingestion import InputFile, group_series, scan_input_directory
from .pipeline import AudioPipeline
from .playlist_service import PlaylistService


logger = get_logger()

# Articles above this word count are split into chapters via LLM.
# Below this threshold they become a single-chapter episode.
DEFAULT_CHAPTERIZE_THRESHOLD = 5000


def _slugify(text: str) -> str:
    """Convert a title into a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-") or "untitled"


class AudiobookCurator:
    """Orchestrates the full curation flow: ingest → generate → persist."""

    def __init__(
        self,
        chapterize_threshold: int = DEFAULT_CHAPTERIZE_THRESHOLD,
        skip_llm: bool = False,
        provider_override: Optional[str] = None,
        diarize: bool = False,
    ):
        self._pipeline = AudioPipeline()
        self._playlists = PlaylistService()
        self._chapterize_threshold = chapterize_threshold
        self._skip_llm = skip_llm
        self._provider_override = provider_override
        self._diarize = diarize

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def curate_from_directory(
        self, input_dir: str | Path
    ) -> dict[str, Any]:
        """Scan a directory and process all text files.

        Returns a summary dict with counts and any errors.
        """
        logger.info(f"[curator] Scanning {input_dir}...")
        inputs = scan_input_directory(input_dir)
        if not inputs:
            logger.info("[curator] No files to process")
            return self._summary(0, 0, [])

        # Separate single articles from series files
        singles = [
            f for f in inputs if f.input_type == "single_article"
        ]
        series_groups = group_series(inputs)

        episodes_generated = 0
        playlists_touched = 0
        errors: list[str] = []

        # Process series groups
        for slug, files in series_groups.items():
            try:
                result = self._process_series(slug, files)
                episodes_generated += result["episodes"]
                playlists_touched += 1
            except Exception as e:
                msg = f"Series '{slug}' failed: {e}"
                logger.error(msg)
                errors.append(msg)

        # Process single articles
        for inp in singles:
            try:
                result = self._process_single_article(inp)
                episodes_generated += result["episodes"]
                playlists_touched += 1
            except Exception as e:
                msg = f"Article '{inp.title}' failed: {e}"
                logger.error(msg)
                errors.append(msg)

        summary = self._summary(
            episodes_generated, playlists_touched, errors
        )
        logger.info(
            f"[curator] Done! {episodes_generated} episode(s) generated, "
            f"{playlists_touched} playlist(s) touched"
        )
        return summary

    def curate_single_text(
        self,
        text: str,
        title: str,
        playlist_slug: Optional[str] = None,
        playlist_title: Optional[str] = None,
        source_url: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Programmatic API: generate audio from raw text and add to a
        playlist.

        If no playlist_slug is given, one is derived from the title.
        """
        slug = playlist_slug or _slugify(title)
        pl_title = playlist_title or title

        playlist = self._playlists.find_or_create_playlist(
            slug=slug,
            title=pl_title,
            playlist_type="collection",
            tags=tags,
        )

        seq = self._playlists.get_next_sequence_number(playlist["id"])
        episode = self._playlists.create_episode(
            playlist_id=playlist["id"],
            title=title,
            sequence_number=seq,
            source_url=source_url,
        )

        should_skip_llm = (
            self._skip_llm or len(text.split()) <= self._chapterize_threshold
        )
        self._generate_and_update(episode, text, should_skip_llm)
        self._playlists.refresh_playlist_stats(playlist["id"])

        return {
            "playlist": self._playlists.get_playlist_by_id(
                playlist["id"]
            ),
            "episode": self._playlists.get_episode_by_id(
                episode["id"]
            ),
        }

    # ------------------------------------------------------------------
    # Internal: Series Processing
    # ------------------------------------------------------------------

    def _process_series(
        self, slug: str, files: list[InputFile]
    ) -> dict[str, int]:
        """Process a group of series files into one playlist."""
        series_title = files[0].series_title or files[0].title
        tags = files[0].tags if files[0].tags else []

        logger.info(
            f"[curator] Series '{series_title}': {len(files)} file(s)"
        )

        playlist = self._playlists.find_or_create_playlist(
            slug=slug,
            title=series_title,
            playlist_type="series",
            tags=tags,
        )

        generated = 0
        for inp in files:
            episode, created = self._playlists.find_or_create_episode(
                playlist_id=playlist["id"],
                title=inp.title,
                sequence_number=inp.sequence_number,
                source_url=inp.source_url,
                description=inp.description,
                metadata={
                    "author": inp.author,
                    "word_count": inp.word_count,
                    "source_file": inp.filepath.name,
                },
            )

            # Series episodes are already logically divided — no LLM
            self._generate_and_update(
                episode, inp.body, skip_llm=True
            )
            generated += 1

        self._playlists.refresh_playlist_stats(playlist["id"])
        return {"episodes": generated}

    # ------------------------------------------------------------------
    # Internal: Single Article Processing
    # ------------------------------------------------------------------

    def _process_single_article(
        self, inp: InputFile
    ) -> dict[str, int]:
        """Process a single standalone article."""
        slug = _slugify(inp.title)
        logger.info(
            f"[curator] Article '{inp.title}' — "
            f"{inp.word_count} words"
        )

        playlist = self._playlists.find_or_create_playlist(
            slug=slug,
            title=inp.title,
            playlist_type="collection",
            description=inp.description,
            tags=inp.tags,
        )

        seq = self._playlists.get_next_sequence_number(playlist["id"])
        episode, created = self._playlists.find_or_create_episode(
            playlist_id=playlist["id"],
            title=inp.title,
            sequence_number=seq,
            source_url=inp.source_url,
            description=inp.description,
            metadata={
                "author": inp.author,
                "word_count": inp.word_count,
                "source_file": inp.filepath.name,
            },
        )

        # Use LLM chapterization only for long articles
        should_skip_llm = (
            self._skip_llm
            or inp.word_count <= self._chapterize_threshold
        )
        self._generate_and_update(episode, inp.body, should_skip_llm)
        self._playlists.refresh_playlist_stats(playlist["id"])
        return {"episodes": 1}

    # ------------------------------------------------------------------
    # Internal: Audio Generation + DB Update
    # ------------------------------------------------------------------

    def _generate_and_update(
        self,
        episode: dict,
        text: str,
        skip_llm: bool,
    ) -> None:
        """Run the audio pipeline and update the episode record.
        
        Skips episodes that already completed (safe for re-runs).
        Re-attempts episodes that are in 'pending' or 'failed' status.
        """
        episode_id = episode["id"]

        # Skip if already successfully generated
        if episode.get("status") == "completed":
            logger.info(
                f"  ↩ Skipping '{episode['title']}' (already completed)"
            )
            return

        # Mark as generating
        self._playlists.update_episode(
            episode_id, {"status": "generating"}
        )

        try:
            result = self._pipeline.generate_episode(
                text=text,
                title=episode["title"],
                output_dir=Path("outputs/audiobooks") / episode_id,
                skip_llm=skip_llm,
                provider_override=self._provider_override,
                diarize=self._diarize,
            )

            audio_url = str(result.audio_path.absolute())
            
            # Optional Supabase upload
            from .storage import upload_to_supabase
            playlist = self._playlists.get_playlist_by_id(episode["playlist_id"])
            playlist_title = playlist["title"] if playlist else "Unknown"
            
            # Use same path format as manual seeds: audiobooks/Playlist_Title/Episode_Title.mp3
            safe_pl_title = "".join(c if c.isalnum() or c in " _-" else "" for c in playlist_title).strip()
            safe_ep_title = "".join(c if c.isalnum() or c in " _-" else "" for c in episode["title"]).replace(" ", "_")
            ext = result.audio_path.suffix
            destination_path = f"{safe_pl_title}/{safe_ep_title}{ext}"
            
            public_url = upload_to_supabase(result.audio_path, "audiobooks", destination_path)
            if public_url:
                audio_url = public_url

            self._playlists.update_episode(
                episode_id,
                {
                    "audio_url": audio_url,
                    "duration_seconds": result.duration_seconds,
                    "chapters": result.chapters,
                    "status": "completed",
                },
            )
            logger.info(
                f"  ✓ Episode '{episode['title']}' — "
                f"{result.duration_seconds}s"
            )
        except Exception as e:
            self._playlists.update_episode(
                episode_id, {"status": "failed"}
            )
            logger.error(
                f"  ✗ Episode '{episode['title']}' failed: {e}"
            )
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _summary(
        episodes: int, playlists: int, errors: list[str]
    ) -> dict[str, Any]:
        return {
            "episodes_generated": episodes,
            "playlists_touched": playlists,
            "errors": errors,
            "success": len(errors) == 0,
        }
