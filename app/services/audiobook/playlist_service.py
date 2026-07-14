"""Database CRUD service for audio playlists and episodes.

Pure data-access layer — no business logic. All methods return dicts
(never raw ORM objects) to avoid detached-session issues.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.database import get_session
from app.logging import get_logger
from app.models import AudioEpisode, AudioPlaylist


logger = get_logger()


class PlaylistService:
    """CRUD operations for audio_playlists and audio_episodes tables."""

    # ------------------------------------------------------------------
    # Playlists
    # ------------------------------------------------------------------

    def find_or_create_playlist(
        self,
        slug: str,
        title: str,
        playlist_type: str = "series",
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Return existing playlist by slug, or create a new one."""
        with get_session() as session:
            pl = (
                session.query(AudioPlaylist)
                .filter_by(slug=slug)
                .first()
            )
            if pl:
                return pl.to_dict()

            pl = AudioPlaylist(
                title=title,
                slug=slug,
                playlist_type=playlist_type,
                description=description,
                tags=tags or [],
                status="draft",
            )
            session.add(pl)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                pl = (
                    session.query(AudioPlaylist)
                    .filter_by(slug=slug)
                    .first()
                )
                if pl:
                    return pl.to_dict()
                raise
            logger.info(f"Created playlist: {title} ({slug})")
            return pl.to_dict()

    def get_playlist_by_slug(self, slug: str) -> Optional[dict]:
        """Fetch a single playlist by slug, including episodes."""
        with get_session() as session:
            pl = (
                session.query(AudioPlaylist)
                .options(joinedload(AudioPlaylist.episodes))
                .filter_by(slug=slug)
                .first()
            )
            return pl.to_dict(include_episodes=True) if pl else None

    def get_playlist_by_id(self, playlist_id: str) -> Optional[dict]:
        """Fetch a single playlist by UUID."""
        with get_session() as session:
            pl = (
                session.query(AudioPlaylist)
                .options(joinedload(AudioPlaylist.episodes))
                .filter_by(id=playlist_id)
                .first()
            )
            return pl.to_dict(include_episodes=True) if pl else None

    def count_playlists(
        self,
        status: Optional[str] = None,
        playlist_type: Optional[str] = None,
    ) -> int:
        """Count total playlists matching the filters."""
        with get_session() as session:
            query = session.query(AudioPlaylist)
            if status:
                query = query.filter_by(status=status)
            if playlist_type:
                query = query.filter_by(playlist_type=playlist_type)
            return query.count()

    def list_playlists(
        self,
        status: Optional[str] = None,
        playlist_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List playlists with optional filters."""
        with get_session() as session:
            query = session.query(AudioPlaylist).order_by(
                AudioPlaylist.updated_at.desc()
            )
            if status:
                query = query.filter_by(status=status)
            if playlist_type:
                query = query.filter_by(playlist_type=playlist_type)
            objs = query.offset(offset).limit(limit).all()
            return [pl.to_dict() for pl in objs]

    def update_playlist(
        self, playlist_id: str, updates: dict
    ) -> Optional[dict]:
        """Update playlist fields."""
        with get_session() as session:
            pl = (
                session.query(AudioPlaylist)
                .filter_by(id=playlist_id)
                .first()
            )
            if not pl:
                return None
            ALLOWED_PLAYLIST_FIELDS = {"title", "slug", "playlist_type", "description", "tags", "status", "cover_image_url"}
            for key, value in updates.items():
                if key in ALLOWED_PLAYLIST_FIELDS and hasattr(pl, key):
                    setattr(pl, key, value)
            pl.updated_at = datetime.now(timezone.utc)
            session.commit()
            return pl.to_dict()

    def refresh_playlist_stats(self, playlist_id: str) -> Optional[dict]:
        """Recalculate total_duration_seconds and episode_count from
        completed episodes."""
        with get_session() as session:
            pl = (
                session.query(AudioPlaylist)
                .filter_by(id=playlist_id)
                .first()
            )
            if not pl:
                return None

            stats = (
                session.query(
                    func.count(AudioEpisode.id),
                    func.coalesce(
                        func.sum(AudioEpisode.duration_seconds), 0
                    ),
                )
                .filter_by(playlist_id=playlist_id, status="completed")
                .first()
            )
            pl.episode_count = stats[0]
            pl.total_duration_seconds = stats[1]
            pl.updated_at = datetime.now(timezone.utc)
            session.commit()
            return pl.to_dict()

    def delete_playlist(self, playlist_id: str) -> bool:
        """Delete a playlist and all its episodes (CASCADE)."""
        with get_session() as session:
            pl = (
                session.query(AudioPlaylist)
                .filter_by(id=playlist_id)
                .first()
            )
            if not pl:
                return False
            session.delete(pl)
            session.commit()
            return True

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

    def find_or_create_episode(
        self,
        playlist_id: str,
        title: str,
        sequence_number: int,
        source_url: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> tuple[dict, bool]:
        """Return an existing episode by (playlist_id, sequence_number),
        or create a new one in 'pending' status.

        Returns:
            (episode_dict, created) — created=True if a new row was inserted.
        """
        with get_session() as session:
            ep = (
                session.query(AudioEpisode)
                .filter_by(
                    playlist_id=playlist_id,
                    sequence_number=sequence_number,
                )
                .first()
            )
            if ep:
                logger.info(
                    f"Episode #{sequence_number} already exists: "
                    f"'{ep.title}' (status={ep.status})"
                )
                return ep.to_dict(), False

            ep = AudioEpisode(
                playlist_id=playlist_id,
                title=title,
                sequence_number=sequence_number,
                source_url=source_url,
                description=description,
                metadata_=metadata or {},
                status="pending",
            )
            session.add(ep)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                ep = (
                    session.query(AudioEpisode)
                    .filter_by(
                        playlist_id=playlist_id,
                        sequence_number=sequence_number,
                    )
                    .first()
                )
                if ep:
                    return ep.to_dict(), False
                raise
            logger.info(
                f"Created episode #{sequence_number}: {title}"
            )
            return ep.to_dict(), True

    # Keep old name as alias for backwards compatibility
    def create_episode(
        self,
        playlist_id: str,
        title: str,
        sequence_number: int,
        source_url: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create a new episode (raises on duplicate). Use
        find_or_create_episode for idempotent behaviour."""
        ep, created = self.find_or_create_episode(
            playlist_id=playlist_id,
            title=title,
            sequence_number=sequence_number,
            source_url=source_url,
            description=description,
            metadata=metadata,
        )
        if not created:
            raise ValueError(
                f"Episode #{sequence_number} already exists in playlist "
                f"{playlist_id}"
            )
        return ep

    def update_episode(
        self, episode_id: str, updates: dict
    ) -> Optional[dict]:
        """Update episode fields (status, audio_url, duration, etc.)."""
        with get_session() as session:
            ep = (
                session.query(AudioEpisode)
                .filter_by(id=episode_id)
                .first()
            )
            if not ep:
                return None
            ALLOWED_EPISODE_FIELDS = {"title", "description", "sequence_number", "audio_url", "duration_seconds", "source_url", "status", "chapters"}
            for key, value in updates.items():
                if key == "metadata":
                    ep.metadata_ = value
                elif key in ALLOWED_EPISODE_FIELDS and hasattr(ep, key):
                    setattr(ep, key, value)
            session.commit()
            return ep.to_dict()

    def get_episode_by_id(self, episode_id: str) -> Optional[dict]:
        """Fetch a single episode by UUID."""
        with get_session() as session:
            ep = (
                session.query(AudioEpisode)
                .filter_by(id=episode_id)
                .first()
            )
            return ep.to_dict() if ep else None

    def get_episodes_for_playlist(
        self, playlist_id: str
    ) -> list[dict]:
        """Get all episodes for a playlist, ordered by sequence."""
        with get_session() as session:
            eps = (
                session.query(AudioEpisode)
                .filter_by(playlist_id=playlist_id)
                .order_by(AudioEpisode.sequence_number)
                .all()
            )
            return [ep.to_dict() for ep in eps]

    def get_next_sequence_number(self, playlist_id: str) -> int:
        """Return the next available sequence_number for a playlist."""
        with get_session() as session:
            result = (
                session.query(
                    func.coalesce(
                        func.max(AudioEpisode.sequence_number), 0
                    )
                )
                .filter_by(playlist_id=playlist_id)
                .scalar()
            )
            return result + 1
