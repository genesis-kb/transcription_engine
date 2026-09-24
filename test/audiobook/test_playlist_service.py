"""Tests for app.services.audiobook.playlist_service — Group 12.

Uses an in-memory SQLite DB with manually created tables to avoid
the JSONB/UUID incompatibility between Postgres models and SQLite.
"""

import uuid
from contextlib import contextmanager
from unittest import mock

import pytest
from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, create_engine, event, text,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy.types import JSON


# ── SQLite-compatible model copies ───────────────────────────────────

class TestBase(DeclarativeBase):
    pass


class TestAudioPlaylist(TestBase):
    __tablename__ = "audio_playlists"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(Text, nullable=False)
    slug = Column(Text, unique=True, nullable=False)
    description = Column(Text)
    playlist_type = Column(Text, nullable=False, default="series")
    cover_image_url = Column(Text)
    tags = Column(JSON, default=list)
    status = Column(Text, nullable=False, default="draft")
    total_duration_seconds = Column(Integer, default=0)
    episode_count = Column(Integer, default=0)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    episodes = relationship(
        "TestAudioEpisode",
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="TestAudioEpisode.sequence_number",
    )

    __table_args__ = (
        Index("idx_playlists_status", "status"),
        Index("idx_playlists_type", "playlist_type"),
    )

    def to_dict(self, include_episodes=False):
        d = {
            "id": str(self.id),
            "title": self.title,
            "slug": self.slug,
            "description": self.description,
            "playlist_type": self.playlist_type,
            "cover_image_url": self.cover_image_url,
            "tags": self.tags or [],
            "status": self.status,
            "total_duration_seconds": self.total_duration_seconds,
            "episode_count": self.episode_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_episodes:
            d["episodes"] = [ep.to_dict() for ep in self.episodes]
        return d


class TestAudioEpisode(TestBase):
    __tablename__ = "audio_episodes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    playlist_id = Column(
        String, ForeignKey("audio_playlists.id", ondelete="CASCADE"), nullable=False,
    )
    title = Column(Text, nullable=False)
    description = Column(Text)
    sequence_number = Column(Integer, nullable=False)
    audio_url = Column(Text)
    duration_seconds = Column(Integer)
    source_url = Column(Text)
    status = Column(Text, nullable=False, default="pending")
    chapters = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime)

    playlist = relationship("TestAudioPlaylist", back_populates="episodes")

    __table_args__ = (
        UniqueConstraint("playlist_id", "sequence_number", name="uq_episodes_playlist_sequence"),
        Index("idx_episodes_playlist", "playlist_id"),
        Index("idx_episodes_status", "status"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "playlist_id": str(self.playlist_id) if self.playlist_id else None,
            "title": self.title,
            "description": self.description,
            "sequence_number": self.sequence_number,
            "audio_url": self.audio_url,
            "duration_seconds": self.duration_seconds,
            "source_url": self.source_url,
            "status": self.status,
            "chapters": self.chapters or [],
            "metadata": self.metadata_ or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    TestBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    @contextmanager
    def _get_session():
        s = Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # Patch both get_session and the ORM model references inside playlist_service
    with mock.patch("app.services.audiobook.playlist_service.get_session", _get_session), \
         mock.patch("app.services.audiobook.playlist_service.AudioPlaylist", TestAudioPlaylist), \
         mock.patch("app.services.audiobook.playlist_service.AudioEpisode", TestAudioEpisode):
        yield _get_session


# ── Group 12: PlaylistService CRUD ───────────────────────────────────

class TestPlaylistService:
    @pytest.fixture(autouse=True)
    def _setup(self, db_session):
        from app.services.audiobook.playlist_service import PlaylistService
        self.svc = PlaylistService()

    def test_create_playlist(self):
        pl = self.svc.find_or_create_playlist(slug="test", title="Test")
        assert pl["slug"] == "test"
        assert pl["id"]

    def test_idempotent_playlist(self):
        pl1 = self.svc.find_or_create_playlist(slug="dup", title="Dup")
        pl2 = self.svc.find_or_create_playlist(slug="dup", title="Dup")
        assert pl1["id"] == pl2["id"]

    def test_create_episode_pending(self):
        pl = self.svc.find_or_create_playlist(slug="ep-test", title="EP")
        ep, created = self.svc.find_or_create_episode(
            playlist_id=pl["id"], title="E1", sequence_number=1,
        )
        assert created is True
        assert ep["status"] == "pending"

    def test_idempotent_episode(self):
        pl = self.svc.find_or_create_playlist(slug="ep-dup", title="EP")
        ep1, c1 = self.svc.find_or_create_episode(
            playlist_id=pl["id"], title="E1", sequence_number=1,
        )
        ep2, c2 = self.svc.find_or_create_episode(
            playlist_id=pl["id"], title="E1", sequence_number=1,
        )
        assert c1 is True
        assert c2 is False
        assert ep1["id"] == ep2["id"]

    def test_update_episode_status(self):
        pl = self.svc.find_or_create_playlist(slug="upd", title="U")
        ep, _ = self.svc.find_or_create_episode(
            playlist_id=pl["id"], title="E1", sequence_number=1,
        )
        updated = self.svc.update_episode(ep["id"], {"status": "completed"})
        assert updated["status"] == "completed"

    def test_refresh_stats_completed_only(self):
        pl = self.svc.find_or_create_playlist(slug="stats", title="S")
        ep1, _ = self.svc.find_or_create_episode(
            playlist_id=pl["id"], title="E1", sequence_number=1,
        )
        ep2, _ = self.svc.find_or_create_episode(
            playlist_id=pl["id"], title="E2", sequence_number=2,
        )
        self.svc.update_episode(ep1["id"], {"status": "completed", "duration_seconds": 60})
        # ep2 stays pending
        refreshed = self.svc.refresh_playlist_stats(pl["id"])
        assert refreshed["episode_count"] == 1
        assert refreshed["total_duration_seconds"] == 60

    def test_next_sequence_empty_playlist(self):
        pl = self.svc.find_or_create_playlist(slug="seq-empty", title="SE")
        assert self.svc.get_next_sequence_number(pl["id"]) == 1

    def test_next_sequence_with_episodes(self):
        pl = self.svc.find_or_create_playlist(slug="seq-3", title="S3")
        for i in range(1, 4):
            self.svc.find_or_create_episode(
                playlist_id=pl["id"], title=f"E{i}", sequence_number=i,
            )
        assert self.svc.get_next_sequence_number(pl["id"]) == 4
