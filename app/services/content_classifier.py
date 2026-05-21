import json
import re
import time
from datetime import datetime, timezone

from google import genai
from google.genai.types import GenerateContentConfig

from app.config import settings
from app.logging import get_logger
from app.services.database_service import get_database_service


logger = get_logger()


class ContentClassifier:
    """Classifies pending content items as technical or non-technical."""

    def __init__(self):
        self._db = get_database_service()
        self.model = settings.config.get(
            "classification_model", "gemini-3-flash-preview"
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
        """Classify all items with status 'pending'.

        Returns:
            Summary dict with counts.
        """
        items = self._db.get_items_by_status("pending", limit=500)
        if not items:
            logger.info("No pending items to classify.")
            return {
                "items_classified": 0,
                "items_approved": 0,
                "items_rejected": 0,
                "errors": [],
            }

        run = self._db.create_pipeline_run(
            started_at=datetime.now(timezone.utc),
        )
        run_id = run["id"] if run else None

        classified = approved = rejected = 0
        errors = []

        for item in items:
            try:
                result = self._classify_item(item)
                classified += 1
                if result["is_technical"]:
                    approved += 1
                else:
                    rejected += 1
            except Exception as e:
                error_msg = f"Error classifying '{item.get('title', item['id'])}': {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        if run_id:
            status = 'failed' if errors else 'success'
            self._db.complete_pipeline_run(
                run_id,
                status=status,
                completed_at=datetime.now(timezone.utc),
            )

        logger.info(
            f"Classification complete: {classified} classified, "
            f"{approved} approved, {rejected} rejected."
        )
        return {
            "items_classified": classified,
            "items_approved": approved,
            "items_rejected": rejected,
            "errors": errors,
        }

    def classify_item_by_id(self, item_db_id: str) -> dict:
        """Classify a single item by its database UUID."""
        item = self._db.get_item_by_id(item_db_id)
        if not item:
            raise ValueError(f"Item not found: {item_db_id}")

        result = self._classify_item(item)
        return result

    def _classify_item(self, item: dict) -> dict:
        """Classify a single item and update its DB record.

        Args:
            item: Row from content_items table (with joined source data).

        Returns:
            Classification result dict.
        """
        source_metadata = item.get("source_metadata", {})
        duration = source_metadata.get("duration") or 0
        
        # Skip items outside duration range
        if duration > 0 and duration < self.min_duration:
            result = {
                "is_technical": False,
                "confidence": 1.0,
                "reason": f"Too short ({duration}s < {self.min_duration}s minimum)",
            }
            self._save_classification(item, result, status="skipped")
            return result
        if duration > 0 and duration > self.max_duration:
            result = {
                "is_technical": False,
                "confidence": 1.0,
                "reason": f"Too long ({duration}s > {self.max_duration}s maximum)",
            }
            self._save_classification(item, result, status="skipped")
            return result

        # Get channel info from joined data
        source_info = item.get("content_source") or {}
        channel_name = source_info.get("name", "")
        # The category isn't normally passed in include_source dict anymore, just default to slug
        channel_category = source_info.get("slug", "unknown")

        title = item.get("title", "")
        description = item.get("description", "")
        tags = source_metadata.get("tags") or []

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

        self._save_classification(item, result, status=status)

        logger.info(
            f"  {'APPROVED' if result['is_technical'] else 'REJECTED'} "
            f"({result['confidence']:.2f}): {title[:60]}"
        )
        return result

    def _save_classification(self, item: dict, result: dict, status: str):
        """Persist classification result to the database."""
        item_id = item["id"]
        source_metadata = item.get("source_metadata", {})
        source_metadata["classification_reason"] = result["reason"]
        source_metadata["classification_confidence"] = result["confidence"]
        
        tech_score = 5 if result["is_technical"] else 1
        
        self._db.update_content_item(
            item_id,
            {
                "technical_score": tech_score,
                "source_metadata": source_metadata,
                "status": status,
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
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        config = GenerateContentConfig(max_output_tokens=1024)

        for attempt in range(4):
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                return self._parse_response(response.text)
            except Exception as e:
                if ("503" in str(e) or "429" in str(e)) and attempt < 3:
                    wait = 2 ** attempt * 5
                    logger.warning(f"Gemini rate limited (attempt {attempt+1}), waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

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
