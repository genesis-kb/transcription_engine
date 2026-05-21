import logging as syslogging

import click
import requests

from app import logging
from app.commands.cli_utils import get_transcription_url


logger = logging.get_logger()


@click.group()
def ingest():
    """Automated YouTube ingestion commands."""
    logging.configure_logger(log_level=syslogging.INFO)


@ingest.command()
def scan():
    """Scan all active channels for new videos."""
    url = get_transcription_url()
    try:
        response = requests.post(f"{url}/ingestion/scan")
        result = response.json()
        if response.status_code == 200:
            logger.info(
                f"Scan complete: {result.get('items_discovered', 0)} new items discovered."
            )
            errors = result.get("errors", [])
            if errors:
                for err in errors:
                    logger.warning(f"  Error: {err}")
        else:
            logger.error(
                f"Scan failed: {result.get('detail', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Scan request failed: {e}")


@ingest.command()
def classify():
    """Classify all pending items using LLM."""
    url = get_transcription_url()
    try:
        response = requests.post(f"{url}/ingestion/classify")
        result = response.json()
        if response.status_code == 200:
            logger.info(
                f"Classification complete: "
                f"{result.get('items_classified', 0)} classified, "
                f"{result.get('items_approved', 0)} approved, "
                f"{result.get('items_rejected', 0)} rejected."
            )
            errors = result.get("errors", [])
            if errors:
                for err in errors:
                    logger.warning(f"  Error: {err}")
        else:
            logger.error(
                f"Classification failed: {result.get('detail', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Classification request failed: {e}")


@ingest.command()
def run():
    """Run full pipeline: scan → classify → queue approved items."""
    url = get_transcription_url()
    try:
        response = requests.post(f"{url}/ingestion/run")
        result = response.json()
        if response.status_code == 200:
            scan = result.get("scan", {})
            classify_data = result.get("classify", {})
            queue = result.get("queue", {})

            logger.info("Full ingestion pipeline complete:")
            logger.info(
                f"  Scan: {scan.get('items_discovered', 0)} items discovered"
            )
            logger.info(
                f"  Classify: {classify_data.get('items_approved', 0)} approved, "
                f"{classify_data.get('items_rejected', 0)} rejected"
            )
            logger.info(
                f"  Queue: {queue.get('items_queued', 0)} items sent to pipeline"
            )
        else:
            logger.error(
                f"Pipeline failed: {result.get('detail', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Pipeline request failed: {e}")


# ── Channel subcommands ─────────────────────────────────────────────────────


@ingest.group()
def sources():
    """Manage monitored content sources."""
    pass


@sources.command(name="list")
def list_sources():
    """List all monitored sources."""
    url = get_transcription_url()
    try:
        response = requests.get(f"{url}/ingestion/sources")
        result = response.json()
        data = result.get("data", [])
        if not data:
            logger.info("No channels configured.")
            return
        for ch in data:
            active = "active" if ch.get("is_active") else "inactive"
            config = ch.get("config", {})
            logger.info(
                f"  [{active}] {ch['name']} "
                f"(priority: {config.get('priority', '-')}, "
                f"category: {config.get('category', '-')}, "
                f"id: {ch['id']})"
            )
    except Exception as e:
        logger.error(f"Failed to list channels: {e}")


@sources.command(name="add")
@click.argument("source_id")
@click.argument("source_name")
@click.option(
    "--category",
    default=None,
    help="Source category (e.g., conference, podcast)",
)
@click.option(
    "--priority", default=3, type=int, help="Priority 1 (high) to 5 (low)"
)
@click.option(
    "--url", "source_url", default=None, help="Full channel/source URL"
)
def add_source(source_id, source_name, category, priority, source_url):
    """Add a content source to monitor. Requires SOURCE_ID and SOURCE_NAME."""
    url = get_transcription_url()
    payload = {
        "slug": source_id,
        "name": source_name,
        "source_type": "youtube",
        "base_url": source_url,
        "config": {
            "yt_channel_id": source_id,
            "priority": priority,
        }
    }
    if category:
        payload["config"]["category"] = category

    try:
        response = requests.post(f"{url}/ingestion/sources", json=payload)
        result = response.json()
        if response.status_code == 200:
            logger.info(f"Source added: {source_name}")
        else:
            logger.error(f"Failed: {result.get('detail', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Failed to add source: {e}")


# ── Item subcommands ────────────────────────────────────────────────────────


@ingest.group()
def items():
    """View and manage discovered items."""
    pass


@items.command(name="list")
@click.option(
    "--status",
    default=None,
    help="Filter by status (pending, classified, queued, in_queue, transcribed, skipped)",
)
@click.option(
    "--technical/--non-technical",
    default=None,
    help="Filter by technical classification",
)
@click.option("--limit", default=50, type=int, help="Max results to show")
def list_items(status, technical, limit):
    """List discovered items."""
    url = get_transcription_url()
    params = {"limit": limit}
    if status:
        params["status"] = status
    if technical is not None:
        params["is_technical"] = technical

    try:
        response = requests.get(f"{url}/ingestion/items", params=params)
        result = response.json()
        data = result.get("data", [])
        if not data:
            logger.info("No items found matching filters.")
            return
        for v in data:
            tech_score = v.get("technical_score")
            tech = (
                "technical"
                if tech_score and tech_score >= 4
                else (
                    "non-technical"
                    if tech_score and tech_score < 4
                    else "unclassified"
                )
            )
            logger.info(
                f"  [{v.get('status', '?')}] [{tech}] "
                f"{v.get('title', 'No title')[:70]} "
                f"(id: {v['id']})"
            )
    except Exception as e:
        logger.error(f"Failed to list items: {e}")


@items.command(name="approve")
@click.argument("item_id")
@click.option("--reason", default=None, help="Reason for approval")
def approve_item(item_id, reason):
    """Manually approve an item for transcription."""
    url = get_transcription_url()
    payload = {"is_technical": True}
    if reason:
        payload["classification_reason"] = reason

    try:
        response = requests.put(
            f"{url}/ingestion/items/{item_id}", json=payload
        )
        result = response.json()
        if response.status_code == 200:
            logger.info("Item approved and queued for transcription.")
        else:
            logger.error(f"Failed: {result.get('detail', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Failed to approve item: {e}")


@items.command(name="reject")
@click.argument("item_id")
@click.option("--reason", default=None, help="Reason for rejection")
def reject_item(item_id, reason):
    """Manually reject an item."""
    url = get_transcription_url()
    payload = {"is_technical": False}
    if reason:
        payload["classification_reason"] = reason

    try:
        response = requests.put(
            f"{url}/ingestion/items/{item_id}", json=payload
        )
        result = response.json()
        if response.status_code == 200:
            logger.info("Item rejected and skipped.")
        else:
            logger.error(f"Failed: {result.get('detail', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Failed to reject item: {e}")


commands = ingest
