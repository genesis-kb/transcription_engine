from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.logging import get_logger
from app.services.ingestion_service import IngestionService


logger = get_logger()

# Global scheduler instance
_scheduler = None


def _run_ingestion_job():
    """Job function to run the full ingestion pipeline."""
    logger.info("Scheduler: Triggering scheduled ingestion pipeline run.")
    try:
        service = IngestionService()
        service.run_full_pipeline()
    except Exception as e:
        logger.error(f"Scheduler: Scheduled ingestion pipeline failed: {e}")


def start_scheduler():
    """Start the background scheduler for periodic tasks."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler is already running.")
        return

    logger.info("Starting background scheduler...")
    _scheduler = BackgroundScheduler()

    # Schedule the ingestion pipeline to run every 5 minutes
    _scheduler.add_job(
        _run_ingestion_job,
        trigger=IntervalTrigger(minutes=5),
        id="ingestion_pipeline",
        name="Run ingestion pipeline periodically",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Background scheduler started successfully.")


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.info("Stopping background scheduler...")
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped.")
