from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.logging import get_logger
from app.services.database_service import get_database_service


logger = get_logger()
router = APIRouter(tags=["Ingestion"])


class SourceCreate(BaseModel):
    name: str
    slug: str
    source_type: str = "youtube"
    base_url: Optional[str] = None
    config: dict = Field(default_factory=dict)
    is_active: bool = True


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    source_type: Optional[str] = None
    base_url: Optional[str] = None
    config: Optional[dict] = None
    is_active: Optional[bool] = None


class ItemOverride(BaseModel):
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
async def scan_all_sources():
    """Trigger a scan of all active sources."""
    from app.services.channel_scanner import ChannelScanner

    try:
        scanner = ChannelScanner()
        result = scanner.scan_all_channels()
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan/{source_id}")
async def scan_source(source_id: str):
    """Trigger a scan of a specific source."""
    from app.services.channel_scanner import ChannelScanner

    try:
        scanner = ChannelScanner()
        result = scanner.scan_channel_by_id(source_id)
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Scan failed for source {source_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources")
async def list_sources():
    """List all monitored sources."""
    db = _get_db()
    data = db.list_sources()
    return {"data": data}


@router.post("/sources")
async def add_source(source: SourceCreate):
    """Add a new source to monitor."""
    db = _get_db()
    result = db.add_source(source.model_dump())
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to add source.")
    return {"status": "success", "data": result}


@router.put("/sources/{source_id}")
async def update_source(source_id: str, updates: SourceUpdate):
    """Update a monitored source."""
    db = _get_db()
    update_data = {
        k: v for k, v in updates.model_dump().items() if v is not None
    }
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")
        

    result = db.update_source(source_id, update_data)
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return {"status": "success", "data": result}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    """Remove a monitored source."""
    db = _get_db()
    success = db.delete_source(source_id)
    if not success:
        raise HTTPException(
            status_code=404, detail="Source not found or delete failed."
        )
    return {"status": "success", "message": "Source deleted."}


@router.post("/classify")
async def classify_all_pending():
    """Classify all pending items using LLM."""
    from app.services.content_classifier import ContentClassifier

    try:
        classifier = ContentClassifier()
        result = classifier.classify_all_pending()
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/classify/{item_id}")
async def classify_item(item_id: str):
    """Classify a specific item."""
    from app.services.content_classifier import ContentClassifier

    try:
        classifier = ContentClassifier()
        result = classifier.classify_item_by_id(item_id)
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Classification failed for item {item_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/items")
async def list_items(
    status: Optional[str] = None,
    is_technical: Optional[bool] = None,
    source_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List discovered items with optional filters."""
    db = _get_db()
    
    data = db.list_content_items(
        status=status,
        is_technical=is_technical,
        source_id=source_id,
        limit=limit,
        offset=offset,
    )
    return {"data": data}


@router.put("/items/{item_id}")
async def override_item(item_id: str, override: ItemOverride):
    """Manually approve or reject an item."""
    db = _get_db()
    from datetime import datetime, timezone
    
    tech_score = 5 if override.is_technical else 1

    updates = {
        "technical_score": tech_score,
        "status": "queued" if override.is_technical else "skipped",
        # Keep source_metadata updated with the reason if we want to preserve it
    }
    
    # Update source_metadata to include reason
    item = db.get_item_by_id(item_id)
    if item:
        meta = item.get("source_metadata", {})
        meta["classification_reason"] = override.classification_reason or "Manual override"
        meta["classification_confidence"] = 1.0
        updates["source_metadata"] = meta

    result = db.update_content_item(item_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    return {"status": "success", "data": result}


@router.get("/runs")
async def list_runs(limit: int = 50):
    """List ingestion run history."""
    db = _get_db()
    data = db.list_pipeline_runs(limit=limit)
    return {"data": data}
