"""Read-only REST API for audiobook playlists and episodes.

Endpoints:
    GET /audiobooks/playlists                   — list all playlists
    GET /audiobooks/playlists/{slug}            — single playlist + episodes
    GET /audiobooks/episodes/{episode_id}       — single episode
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.logging import get_logger
from app.services.audiobook.playlist_service import PlaylistService


logger = get_logger()
router = APIRouter(tags=["Audiobooks"])


def _service() -> PlaylistService:
    return PlaylistService()


# ─────────────────────────────────────────────────────────────────────────────
# GET /audiobooks/playlists
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/playlists")
async def list_playlists(
    status: Optional[str] = Query(
        None,
        description="Filter by status: draft | published | archived",
    ),
    playlist_type: Optional[str] = Query(
        None,
        description="Filter by type: series | collection",
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List all audio playlists.

    Returns playlists ordered by last updated (newest first).
    Does NOT include episodes — use /playlists/{slug} for that.
    """
    try:
        playlists = _service().list_playlists(
            status=status,
            playlist_type=playlist_type,
            limit=limit,
            offset=offset,
        )
        return {"data": playlists, "total": len(playlists)}
    except Exception as e:
        logger.error(f"Failed to list playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GET /audiobooks/playlists/{slug}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/playlists/{slug}")
async def get_playlist(slug: str):
    """Get a single playlist by slug, including all ordered episodes.

    Episodes are sorted by sequence_number ascending.
    Episodes with status != 'completed' will have audio_url = null.
    """
    try:
        playlist = _service().get_playlist_by_slug(slug)
        if not playlist:
            raise HTTPException(
                status_code=404,
                detail=f"Playlist '{slug}' not found.",
            )
        return {"data": playlist}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get playlist '{slug}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GET /audiobooks/episodes/{episode_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/episodes/{episode_id}")
async def get_episode(episode_id: str):
    """Get a single episode by UUID.

    Useful for deep-linking directly to a specific episode.
    """
    try:
        episode = _service().get_episode_by_id(episode_id)
        if not episode:
            raise HTTPException(
                status_code=404,
                detail=f"Episode '{episode_id}' not found.",
            )
        return {"data": episode}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get episode '{episode_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
