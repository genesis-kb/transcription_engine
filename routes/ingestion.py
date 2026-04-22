from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.logging import get_logger
from app.services.database_service import get_database_service


logger = get_logger()
router = APIRouter(tags=["Ingestion"])


class ChannelCreate(BaseModel):
    channel_id: str
    channel_name: str
    channel_url: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: int = 3
    is_active: bool = True


class ChannelUpdate(BaseModel):
    channel_name: Optional[str] = None
    channel_url: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class VideoOverride(BaseModel):
    is_technical: bool
    classification_reason: Optional[str] = None


def _get_db():
    db = get_database_service()
    if not db.is_available:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Set DATABASE_URL environment variable.",
        )
    return db


@router.post("/run")
async def run_full_pipeline():
    """Run the full ingestion pipeline: scan → classify → queue."""
    from app.services.ingestion_service import IngestionService

    try:
        service = IngestionService()
        result = service.run_full_pipeline()
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan")
async def scan_all_channels():
    """Trigger a scan of all active channels."""
    from app.services.channel_scanner import ChannelScanner

    try:
        scanner = ChannelScanner()
        result = scanner.scan_all_channels()
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan/{channel_id}")
async def scan_channel(channel_id: str):
    """Trigger a scan of a specific channel."""
    from app.services.channel_scanner import ChannelScanner

    try:
        scanner = ChannelScanner()
        result = scanner.scan_channel_by_id(channel_id)
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Scan failed for channel {channel_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels")
async def list_channels():
    """List all monitored channels."""
    db = _get_db()
    data = db.list_channels()
    return {"data": data}


@router.post("/channels")
async def add_channel(channel: ChannelCreate):
    """Add a new channel to monitor."""
    db = _get_db()
    result = db.add_channel(channel.model_dump())
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to add channel.")
    return {"status": "success", "data": result}


@router.put("/channels/{channel_id}")
async def update_channel(channel_id: str, updates: ChannelUpdate):
    """Update a monitored channel."""
    db = _get_db()
    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")
    result = db.update_channel(channel_id, update_data)
    if result is None:
        raise HTTPException(status_code=404, detail="Channel not found.")
    return {"status": "success", "data": result}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str):
    """Remove a monitored channel."""
    db = _get_db()
    success = db.delete_channel(channel_id)
    if not success:
        raise HTTPException(
            status_code=404, detail="Channel not found or delete failed."
        )
    return {"status": "success", "message": "Channel deleted."}


@router.post("/classify")
async def classify_all_pending():
    """Classify all pending videos using LLM."""
    from app.services.content_classifier import ContentClassifier

    try:
        classifier = ContentClassifier()
        result = classifier.classify_all_pending()
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/classify/{video_id}")
async def classify_video(video_id: str):
    """Classify a specific video."""
    from app.services.content_classifier import ContentClassifier

    try:
        classifier = ContentClassifier()
        result = classifier.classify_video_by_id(video_id)
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Classification failed for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/videos")
async def list_videos(
    status: Optional[str] = None,
    is_technical: Optional[bool] = None,
    channel_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List discovered videos with optional filters."""
    db = _get_db()
    data = db.list_youtube_videos(
        status=status,
        is_technical=is_technical,
        channel_id=channel_id,
        limit=limit,
        offset=offset,
    )
    return {"data": data}


@router.put("/videos/{video_id}")
async def override_video(video_id: str, override: VideoOverride):
    """Manually approve or reject a video."""
    db = _get_db()
    from datetime import datetime, timezone

    updates = {
        "is_technical": override.is_technical,
        "classification_reason": override.classification_reason
        or "Manual override",
        "classification_confidence": 1.0,
        "status": "queued" if override.is_technical else "skipped",
        "classified_at": datetime.now(timezone.utc).isoformat(),
    }
    result = db.update_youtube_video(video_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Video not found.")
    return {"status": "success", "data": result}


@router.get("/runs")
async def list_runs(limit: int = 50):
    """List ingestion run history."""
    db = _get_db()
    data = db.list_ingestion_runs(limit=limit)
    return {"data": data}
