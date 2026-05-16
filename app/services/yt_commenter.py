"""YouTube Auto-Commenter Service.

Posts transcript summaries as top-level comments on YouTube videos.
Supports both manual API calls and automatic pipeline integration.
"""

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from googleapiclient.errors import HttpError

from app.config import settings
from app.logging import get_logger
from app.services.database_service import get_database_service


logger = get_logger()


class YouTubeCommenterService:
    """Service for posting transcript summaries as YouTube comments."""

    def __init__(self):
        self._youtube = None
        self._db = get_database_service()

    @property
    def youtube(self):
        """Lazy-load authenticated YouTube service (needs OAuth)."""
        if self._youtube is None:
            from app.services.youtube_auth import get_authenticated_youtube_service

            self._youtube = get_authenticated_youtube_service()
        return self._youtube

    def comment_on_video(self, video_url: str) -> dict:
        """Post a summary comment on a YouTube video by looking up its transcript.

        Args:
            video_url: Full YouTube video URL.

        Returns:
            Dict with comment details or error info.

        Raises:
            ValueError: If URL is invalid or no transcript found.
        """
        video_id = self._extract_video_id(video_url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {video_url}")

        # Check if we already commented on this video
        existing = self._db.get_yt_comment_by_video_id(video_id)
        if existing:
            logger.info(f"Already commented on video {video_id}, skipping.")
            return {
                "status": "already_commented",
                "video_id": video_id,
                "comment_id": existing["comment_id"],
                "posted_at": existing["posted_at"],
            }

        # Look up transcript in DB
        transcript = self._db.get_transcript_by_video_id(video_id)
        if not transcript:
            raise ValueError(
                f"No transcript found for video {video_id}. "
                f"Transcribe the video first."
            )

        summary = transcript.get("summary")
        if not summary:
            raise ValueError(
                f"Transcript for video {video_id} has no summary. "
                f"Run summarization first."
            )

        title = transcript.get("title", "")
        loc = transcript.get("loc", "")
        transcript_id = transcript.get("id")

        comment_text = self._format_comment(title, summary, loc)
        return self._post_comment(video_id, comment_text, transcript_id)

    def comment_with_summary(
        self, video_url: str, summary: str, title: str = "", loc: str = ""
    ) -> dict:
        """Post a provided summary as a comment (bypass DB lookup).

        Args:
            video_url: Full YouTube video URL.
            summary: Summary text to post.
            title: Optional transcript title.
            loc: Optional location/category for transcript link.

        Returns:
            Dict with comment details.
        """
        video_id = self._extract_video_id(video_url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {video_url}")

        # Check duplicate
        existing = self._db.get_yt_comment_by_video_id(video_id)
        if existing:
            logger.info(f"Already commented on video {video_id}, skipping.")
            return {
                "status": "already_commented",
                "video_id": video_id,
                "comment_id": existing["comment_id"],
                "posted_at": existing["posted_at"],
            }

        comment_text = self._format_comment(title, summary, loc)
        return self._post_comment(video_id, comment_text, transcript_id=None)

    def comment_from_transcript_object(self, transcript, video_url: str) -> Optional[dict]:
        """Post a comment using an in-memory Transcript object.

        Called automatically from the transcription pipeline after
        summarization completes.

        Args:
            transcript: app.transcript.Transcript object with .summary populated.
            video_url: The YouTube video URL that was transcribed.

        Returns:
            Comment details dict, or None on failure.
        """
        video_id = self._extract_video_id(video_url)
        if not video_id:
            logger.warning(f"Cannot comment: invalid video URL '{video_url}'")
            return None

        summary = transcript.summary
        if not summary:
            logger.warning(f"Cannot comment on {video_id}: no summary available.")
            return None

        # Check duplicate
        existing = self._db.get_yt_comment_by_video_id(video_id)
        if existing:
            logger.info(f"Already commented on video {video_id}, skipping.")
            return {
                "status": "already_commented",
                "video_id": video_id,
                "comment_id": existing["comment_id"],
            }

        title = transcript.title or ""
        loc = transcript.source.loc if hasattr(transcript, "source") else ""

        comment_text = self._format_comment(title, summary, loc)

        try:
            return self._post_comment(video_id, comment_text, transcript_id=None)
        except Exception as e:
            logger.error(f"Failed to auto-comment on video {video_id}: {e}")
            return None

    def delete_comment(self, video_id: str) -> dict:
        """Delete a previously posted comment from YouTube.

        Args:
            video_id: YouTube video ID.

        Returns:
            Status dict.
        """
        record = self._db.get_yt_comment_by_video_id(video_id)
        if not record:
            raise ValueError(f"No comment record found for video {video_id}")

        comment_id = record["comment_id"]
        try:
            self.youtube.comments().delete(id=comment_id).execute()
            self._db.update_yt_comment_status(record["id"], "deleted")
            logger.info(f"Deleted comment {comment_id} from video {video_id}.")
            return {"status": "deleted", "video_id": video_id, "comment_id": comment_id}
        except HttpError as e:
            logger.error(f"Failed to delete comment {comment_id}: {e}")
            raise

    def get_comment_status(self, video_id: str) -> dict:
        """Check if we've already commented on a video.

        Args:
            video_id: YouTube video ID.

        Returns:
            Comment record or not-found status.
        """
        record = self._db.get_yt_comment_by_video_id(video_id)
        if record:
            return {"status": "found", "data": record}
        return {"status": "not_found", "video_id": video_id}

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _post_comment(
        self, video_id: str, comment_text: str, transcript_id: Optional[str]
    ) -> dict:
        """Post a top-level comment on a YouTube video.

        Args:
            video_id: YouTube video ID.
            comment_text: Formatted comment text.
            transcript_id: Optional DB transcript UUID to link.

        Returns:
            Dict with posted comment details.
        """
        try:
            request = self.youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": comment_text,
                            }
                        },
                    }
                },
            )
            response = request.execute()

            yt_comment_id = response["id"]
            posted_at = response["snippet"]["topLevelComment"]["snippet"][
                "publishedAt"
            ]

            # Save to DB
            comment_data = {
                "video_id": video_id,
                "comment_id": yt_comment_id,
                "transcript_id": transcript_id,
                "comment_text": comment_text,
                "status": "posted",
            }
            self._db.save_yt_comment(comment_data)

            logger.info(
                f"Posted comment on video {video_id} (comment: {yt_comment_id})"
            )

            return {
                "status": "posted",
                "video_id": video_id,
                "comment_id": yt_comment_id,
                "comment_text": comment_text,
                "posted_at": posted_at,
            }

        except HttpError as e:
            error_detail = str(e)
            logger.error(f"YouTube API error posting comment on {video_id}: {error_detail}")

            # Save failed attempt to DB
            self._db.save_yt_comment(
                {
                    "video_id": video_id,
                    "comment_id": None,
                    "transcript_id": transcript_id,
                    "comment_text": comment_text,
                    "status": "failed",
                }
            )
            raise

    def _format_comment(self, title: str, summary: str, loc: str = "") -> str:
        """Format a transcript summary into a YouTube comment.

        Args:
            title: Transcript title.
            summary: Summary text.
            loc: Location/category path for building the transcript URL.

        Returns:
            Formatted comment string.
        """
        lines = ["📝 AI-Generated Transcript Summary", ""]

        if title:
            lines.append(f"📌 {title}")
            lines.append("")

        lines.append(summary)
        lines.append("")
        lines.append("---")

        # Build transcript link if we have a location
        if loc and title:
            slug = _slugify(title)
            transcript_url = f"{_get_btc_transcripts_url()}/{loc}/{slug}"
            lines.append(f"🔗 Full transcript: {transcript_url}")

        lines.append("🤖 Generated by BitScribe Transcription Engine")

        return "\n".join(lines)

    @staticmethod
    def _extract_video_id(url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats.

        Supports:
            - https://www.youtube.com/watch?v=VIDEO_ID
            - https://youtu.be/VIDEO_ID
            - https://www.youtube.com/shorts/VIDEO_ID
            - https://www.youtube.com/embed/VIDEO_ID
            - Plain video ID string (11 chars)

        Args:
            url: YouTube URL or video ID.

        Returns:
            Video ID string, or None if extraction fails.
        """
        if not url:
            return None

        # Plain video ID (11 alphanumeric chars + hyphens/underscores)
        if re.match(r"^[A-Za-z0-9_-]{11}$", url):
            return url

        try:
            parsed = urlparse(url)

            # youtu.be/VIDEO_ID
            if parsed.hostname in ("youtu.be",):
                return parsed.path.lstrip("/").split("/")[0] or None

            # youtube.com/watch?v=VIDEO_ID
            if parsed.hostname in (
                "www.youtube.com",
                "youtube.com",
                "m.youtube.com",
            ):
                if parsed.path == "/watch":
                    params = parse_qs(parsed.query)
                    video_ids = params.get("v", [])
                    return video_ids[0] if video_ids else None

                # /shorts/VIDEO_ID or /embed/VIDEO_ID
                for prefix in ("/shorts/", "/embed/", "/v/"):
                    if parsed.path.startswith(prefix):
                        return parsed.path[len(prefix):].split("/")[0] or None

        except Exception:
            pass

        return None


def _slugify(text: str) -> str:
    """Simple slugify for building URLs."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-")


def _get_btc_transcripts_url() -> str:
    """Get the base URL for transcript links."""
    try:
        return settings.BTC_TRANSCRIPTS_URL.rstrip("/")
    except Exception:
        return "https://btctranscripts.com"
