import json
import re
from datetime import datetime, timezone

from app.config import settings
from app.logging import get_logger
from app.services.database_service import get_database_service
from app.services.llm_service import call_llm


logger = get_logger()


class ContentClassifier:
    """Classifies pending YouTube videos as technical or non-technical."""

    def __init__(self):
        self._db = get_database_service()
        self.model = settings.config.get(
            "classification_model", "gemini:gemini-3-flash-preview"
        )
        self.confidence_threshold = float(
            settings.config.get("classification_confidence_threshold", "0.7")
        )
        self.min_duration = int(
            settings.config.get("classification_min_duration", "600")
        )
        self.max_duration = int(
            settings.config.get("classification_max_duration", "3000")
        )

    def classify_all_pending(self) -> dict:
        """Classify all videos with status 'pending'.

        Returns:
            Summary dict with counts.
        """
        videos = self._db.get_videos_by_status("pending", limit=500)
        if not videos:
            logger.info("No pending videos to classify.")
            return {
                "videos_classified": 0,
                "videos_approved": 0,
                "videos_rejected": 0,
                "errors": [],
            }

        run = self._db.create_ingestion_run(
            run_type="classify",
            started_at=datetime.now(timezone.utc),
        )
        run_id = run["id"] if run else None

        classified = approved = rejected = 0
        errors = []

        for video in videos:
            try:
                result = self._classify_video(video)
                classified += 1
                if result["is_technical"]:
                    approved += 1
                else:
                    rejected += 1
            except Exception as e:
                error_msg = f"Error classifying '{video.get('title', video['id'])}': {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        if run_id:
            self._db.complete_ingestion_run(
                run_id,
                videos_classified=classified,
                videos_approved=approved,
                videos_rejected=rejected,
                errors=errors,
                completed_at=datetime.now(timezone.utc),
            )

        logger.info(
            f"Classification complete: {classified} classified, "
            f"{approved} approved, {rejected} rejected."
        )
        return {
            "videos_classified": classified,
            "videos_approved": approved,
            "videos_rejected": rejected,
            "errors": errors,
        }

    def classify_video_by_id(self, video_db_id: str) -> dict:
        """Classify a single video by its database UUID."""
        video = self._db.get_video_by_id(video_db_id)
        if not video:
            raise ValueError(f"Video not found: {video_db_id}")

        result = self._classify_video(video)
        return result

    def _classify_video(self, video: dict) -> dict:
        """Classify a single video and update its DB record.

        Args:
            video: Row from youtube_videos table (with joined channel data).

        Returns:
            Classification result dict.
        """
        # Skip videos outside duration range
        duration = video.get("duration") or 0
        if duration > 0 and duration < self.min_duration:
            result = {
                "is_technical": False,
                "confidence": 1.0,
                "reason": f"Too short ({duration}s < {self.min_duration}s minimum)",
            }
            self._save_classification(video["id"], result, status="skipped")
            return result
        if duration > 0 and duration > self.max_duration:
            result = {
                "is_technical": False,
                "confidence": 1.0,
                "reason": f"Too long ({duration}s > {self.max_duration}s maximum)",
            }
            self._save_classification(video["id"], result, status="skipped")
            return result

        # Get channel info from joined data
        channel_info = video.get("youtube_channels") or {}
        channel_category = channel_info.get("category", "unknown")
        channel_name = channel_info.get("channel_name", "")

        title = video.get("title", "")
        description = video.get("description", "")
        tags = video.get("tags") or []

        prompt = self._build_prompt(
            title, description, tags, channel_name, channel_category
        )

        result = self._call_llm(prompt)

        # Determine status based on classification
        if (
            result["is_technical"]
            and result["confidence"] >= self.confidence_threshold
        ):
            status = "queued"
        elif not result["is_technical"]:
            status = "skipped"
        else:
            # Technical but low confidence — stay classified, don't auto-queue
            status = "classified"

        self._save_classification(video["id"], result, status=status)

        logger.info(
            f"  {'APPROVED' if result['is_technical'] else 'REJECTED'} "
            f"({result['confidence']:.2f}): {title[:60]}"
        )
        return result

    def _save_classification(self, video_id: str, result: dict, status: str):
        """Persist classification result to the database."""
        self._db.update_youtube_video(
            video_id,
            {
                "is_technical": result["is_technical"],
                "classification_reason": result["reason"],
                "classification_confidence": result["confidence"],
                "status": status,
                "classified_at": datetime.now(timezone.utc),
            },
        )

    def _build_prompt(
        self, title, description, tags, channel_name, channel_category
    ) -> str:
        """Build the classification prompt."""
        desc_truncated = (
            description[:1000]
            if description and len(description) > 1000
            else (description or "")
        )
        tags_str = ", ".join(tags[:20]) if tags else "None"

        return (
            "You are a content classifier for a Bitcoin technical transcription archive.\n\n"
            "Your job: decide whether this YouTube video contains **technical Bitcoin content**\n"
            "worth transcribing for developers, researchers, and protocol engineers.\n\n"
            "--- APPROVE (is_technical = true) ---\n"
            "- Conference talks, panels, workshops on Bitcoin protocol, Lightning, mining, cryptography\n"
            "- Developer discussions, code walkthroughs, BIP reviews\n"
            "- Technical deep-dives on consensus, scripting, security, privacy\n"
            "- Educational content explaining Bitcoin internals\n"
            "- Podcast episodes with substantive technical discussion\n\n"
            "--- REJECT (is_technical = false) ---\n"
            "- Price/market commentary, trading analysis\n"
            "- General news roundups, announcements-only content\n"
            "- Promotional content, sponsor reads, product reviews\n"
            "- Non-Bitcoin crypto content (altcoins, DeFi, NFTs)\n"
            "- Short clips (< 3 minutes) that are just teasers or highlights\n"
            "- Lifestyle/culture content tangentially related to Bitcoin\n\n"
            f"--- Video Metadata ---\n"
            f"Title: {title}\n"
            f"Channel: {channel_name}\n"
            f"Channel Category: {channel_category}\n"
            f"Tags: {tags_str}\n"
            f"Description:\n{desc_truncated}\n"
            f"--- End Metadata ---\n\n"
            "Respond with a JSON object only (no markdown):\n"
            '{"is_technical": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}\n'
        )

    def _call_llm(self, prompt: str) -> dict:
        """Call the LLM and parse its classification response."""
        response_text = call_llm(self.model, prompt, max_tokens=1024)
        return self._parse_response(response_text)

    @staticmethod
    def _parse_response(response_text: str) -> dict:
        """Parse the LLM JSON response with fallback handling."""
        try:
            text = response_text.strip()

            # Strip markdown code fences
            if "```" in text:
                match = re.search(
                    r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL
                )
                if match:
                    text = match.group(1).strip()

            # If still not valid JSON, try to extract a JSON object from the text
            if not text.startswith("{"):
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if match:
                    text = match.group(0)

            result = json.loads(text)

            is_technical = bool(result.get("is_technical", False))
            confidence = float(result.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            reason = (
                str(result.get("reason", "")).strip() or "No reason provided"
            )

            return {
                "is_technical": is_technical,
                "confidence": confidence,
                "reason": reason,
            }
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse classification response: {e}")
            logger.warning(f"Raw response: {response_text}")
            return {
                "is_technical": False,
                "confidence": 0.0,
                "reason": f"Parse error: {e}",
            }
