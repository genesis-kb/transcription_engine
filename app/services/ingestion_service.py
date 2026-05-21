from app.logging import get_logger
from app.services.channel_scanner import ChannelScanner
from app.services.content_classifier import ContentClassifier
from app.services.database_service import get_database_service


logger = get_logger()


class IngestionService:
    """Orchestrates the full ingestion pipeline."""

    def __init__(self):
        self._db = get_database_service()

    def run_full_pipeline(self) -> dict:
        """Execute the full pipeline: scan → classify → queue approved items.

        Returns:
            Combined summary of all stages.
        """
        logger.info("Starting full ingestion pipeline...")

        # Stage 1: Scan
        logger.info("Stage 1: Scanning channels for new content...")
        scanner = ChannelScanner()
        scan_result = scanner.scan_all_channels()
        logger.info(
            f"Scan complete: {scan_result['items_discovered']} items discovered."
        )

        # Stage 2: Classify
        logger.info("Stage 2: Classifying pending items...")
        classifier = ContentClassifier()
        classify_result = classifier.classify_all_pending()
        logger.info(
            f"Classification complete: {classify_result['items_approved']} approved, "
            f"{classify_result['items_rejected']} rejected."
        )

        # Stage 3: Queue approved items into transcription pipeline
        logger.info("Stage 3: Queueing approved items for transcription...")
        queue_result = self.queue_approved_items()
        logger.info(
            f"Queueing complete: {queue_result['items_queued']} items sent to pipeline."
        )

        summary = {
            "scan": scan_result,
            "classify": classify_result,
            "queue": queue_result,
        }

        all_errors = (
            scan_result.get("errors", [])
            + classify_result.get("errors", [])
            + queue_result.get("errors", [])
        )
        if all_errors:
            logger.warning(
                f"Pipeline completed with {len(all_errors)} error(s)."
            )

        logger.info("Full ingestion pipeline complete.")
        return summary

    def queue_approved_items(self, limit: int = 20) -> dict:
        """Queue approved items into the transcription pipeline.

        Fetches items with status 'queued' and submits them to the
        transcription API endpoint.

        Args:
            limit: Max number of items to queue per run.

        Returns:
            Summary dict with counts and errors.
        """
        items = self._db.get_items_by_status("queued", limit=limit)
        if not items:
            logger.info("No approved items to queue for transcription.")
            return {"items_queued": 0, "errors": []}

        queued = 0
        errors = []

        for item in items:
            try:
                self._submit_to_pipeline(item)
                queued += 1
            except Exception as e:
                error_msg = f"Failed to queue '{item.get('title', item['external_id'])}': {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return {"items_queued": queued, "errors": errors}

    def _submit_to_pipeline(self, item: dict):
        """Submit a single item to the transcription pipeline via internal API.

        Args:
            item: Row from content_items table with joined source data.
        """
        url = item.get("url")
        if not url:
            url = f"https://www.youtube.com/watch?v={item['external_id']}"

        source_info = item.get("content_source") or {}
        source_slug = source_info.get("slug", "misc")

        import requests

        from app.config import settings

        server_url = (
            settings.TRANSCRIPTION_SERVER_URL or "http://localhost:8000"
        )

        data = {
            "source": url,
            "loc": source_slug,
            "deepgram": True,
            "diarize": True,
            "markdown": True,
            "correct": True,
            "username": "ingestion_bot",
        }

        # Add to queue
        response = requests.post(
            f"{server_url}/transcription/add_to_queue/", data=data
        )
        response.raise_for_status()

        # Update item status
        self._db.update_content_item(
            item["id"],
            {"status": "in_queue"},
        )

        logger.info(f"Queued for transcription: {item.get('title', item['external_id'])}")
