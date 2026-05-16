"""FastAPI routes for the YouTube auto-commenter service."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.logging import get_logger
from app.services.database_service import get_database_service


logger = get_logger()
router = APIRouter(tags=["YouTube Bot"])


class CommentRequest(BaseModel):
    video_url: str


class CommentWithSummaryRequest(BaseModel):
    video_url: str
    summary: str
    title: Optional[str] = ""
    loc: Optional[str] = ""


def _get_db():
    db = get_database_service()
    if not db.is_available:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Set DATABASE_URL environment variable.",
        )
    return db


@router.post("/comment")
async def post_comment(request: CommentRequest):
    """Post a transcript summary as a comment on a YouTube video.

    Looks up the transcript in the database by video URL, retrieves the
    summary, and posts it as a top-level YouTube comment.
    """
    from app.services.yt_commenter import YouTubeCommenterService

    try:
        service = YouTubeCommenterService()
        result = service.comment_on_video(request.video_url)
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to post comment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comment-with-summary")
async def post_comment_with_summary(request: CommentWithSummaryRequest):
    """Post a custom summary as a comment on a YouTube video.

    Use this endpoint to post a manually provided summary instead of
    looking up the transcript from the database.
    """
    from app.services.yt_commenter import YouTubeCommenterService

    try:
        service = YouTubeCommenterService()
        result = service.comment_with_summary(
            video_url=request.video_url,
            summary=request.summary,
            title=request.title,
            loc=request.loc,
        )
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to post comment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comments")
async def list_comments(limit: int = 50, offset: int = 0):
    """List all YouTube comments posted by the bot."""
    db = _get_db()
    data = db.list_yt_comments(limit=limit, offset=offset)
    return {"data": data}


@router.get("/comments/{video_id}")
async def get_comment_status(video_id: str):
    """Check if we've already commented on a specific video."""
    from app.services.yt_commenter import YouTubeCommenterService

    service = YouTubeCommenterService()
    result = service.get_comment_status(video_id)
    return {"data": result}


@router.delete("/comments/{video_id}")
async def delete_comment(video_id: str):
    """Delete a previously posted comment from YouTube."""
    from app.services.yt_commenter import YouTubeCommenterService

    try:
        service = YouTubeCommenterService()
        result = service.delete_comment(video_id)
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete comment: {e}")
        raise HTTPException(status_code=500, detail=str(e))
