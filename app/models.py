"""SQLAlchemy ORM models for the transcription engine database."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class YouTubeChannel(Base):
    __tablename__ = "youtube_channels"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    channel_id = Column(Text, unique=True, nullable=False)
    channel_name = Column(Text, nullable=False)
    channel_url = Column(Text)
    description = Column(Text)
    category = Column(Text)
    priority = Column(Integer, default=3)
    is_active = Column(Boolean, default=True)
    last_scanned_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    videos = relationship(
        "YouTubeVideo", back_populates="channel", cascade="all, delete-orphan"
    )
    ingestion_runs = relationship("IngestionRun", back_populates="channel")

    def to_dict(self):
        return {
            "id": str(self.id),
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "channel_url": self.channel_url,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "is_active": self.is_active,
            "last_scanned_at": self.last_scanned_at.isoformat()
            if self.last_scanned_at
            else None,
            "created_at": self.created_at.isoformat()
            if self.created_at
            else None,
            "updated_at": self.updated_at.isoformat()
            if self.updated_at
            else None,
        }


class YouTubeVideo(Base):
    __tablename__ = "youtube_videos"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    video_id = Column(Text, unique=True, nullable=False)
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("youtube_channels.id", ondelete="CASCADE"),
    )
    title = Column(Text)
    description = Column(Text)
    published_at = Column(DateTime(timezone=True))
    duration = Column(Integer)
    tags = Column(ARRAY(Text), default=[])
    thumbnail_url = Column(Text)
    view_count = Column(Integer)
    is_technical = Column(Boolean)
    classification_reason = Column(Text)
    classification_confidence = Column(Float)
    status = Column(Text, default="pending")
    transcript_id = Column(UUID(as_uuid=True))
    discovered_at = Column(
        DateTime(timezone=True), server_default=text("now()")
    )
    classified_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    channel = relationship("YouTubeChannel", back_populates="videos")

    def to_dict(self, include_channel=False):
        d = {
            "id": str(self.id),
            "video_id": self.video_id,
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "title": self.title,
            "description": self.description,
            "published_at": self.published_at.isoformat()
            if self.published_at
            else None,
            "duration": self.duration,
            "tags": self.tags or [],
            "thumbnail_url": self.thumbnail_url,
            "view_count": self.view_count,
            "is_technical": self.is_technical,
            "classification_reason": self.classification_reason,
            "classification_confidence": self.classification_confidence,
            "status": self.status,
            "transcript_id": str(self.transcript_id)
            if self.transcript_id
            else None,
            "discovered_at": self.discovered_at.isoformat()
            if self.discovered_at
            else None,
            "classified_at": self.classified_at.isoformat()
            if self.classified_at
            else None,
            "created_at": self.created_at.isoformat()
            if self.created_at
            else None,
            "updated_at": self.updated_at.isoformat()
            if self.updated_at
            else None,
        }
        if include_channel and self.channel:
            d["youtube_channels"] = {
                "channel_name": self.channel.channel_name,
                "category": self.channel.category,
            }
        else:
            d["youtube_channels"] = None
        return d


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_type = Column(Text, nullable=False)
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("youtube_channels.id", ondelete="SET NULL"),
    )
    videos_discovered = Column(Integer, default=0)
    videos_classified = Column(Integer, default=0)
    videos_approved = Column(Integer, default=0)
    videos_rejected = Column(Integer, default=0)
    errors = Column(JSONB, default=[])
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    channel = relationship("YouTubeChannel", back_populates="ingestion_runs")

    def to_dict(self, include_channel=False):
        d = {
            "id": str(self.id),
            "run_type": self.run_type,
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "videos_discovered": self.videos_discovered,
            "videos_classified": self.videos_classified,
            "videos_approved": self.videos_approved,
            "videos_rejected": self.videos_rejected,
            "errors": self.errors or [],
            "started_at": self.started_at.isoformat()
            if self.started_at
            else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "created_at": self.created_at.isoformat()
            if self.created_at
            else None,
        }
        if include_channel and self.channel:
            d["youtube_channels"] = {
                "channel_name": self.channel.channel_name,
            }
        else:
            d["youtube_channels"] = None
        return d


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title = Column(Text)
    loc = Column(Text)
    event_date = Column(Text)
    speakers = Column(ARRAY(Text), default=[])
    tags = Column(ARRAY(Text), default=[])
    categories = Column(ARRAY(Text), default=[])
    raw_text = Column(Text)
    corrected_text = Column(Text)
    summary = Column(Text)
    media_url = Column(Text)
    status = Column(Text)
    conference = Column(Text)
    topics = Column(ARRAY(Text), default=[])
    channel_name = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "loc": self.loc,
            "event_date": self.event_date,
            "speakers": self.speakers or [],
            "tags": self.tags or [],
            "categories": self.categories or [],
            "raw_text": self.raw_text,
            "corrected_text": self.corrected_text,
            "summary": self.summary,
            "media_url": self.media_url,
            "status": self.status,
            "conference": self.conference,
            "topics": self.topics or [],
            "channel_name": self.channel_name,
            "created_at": self.created_at.isoformat()
            if self.created_at
            else None,
            "updated_at": self.updated_at.isoformat()
            if self.updated_at
            else None,
        }

class RSSFeed(Base):
    __tablename__ = "rss_feeds"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    feed_url = Column(Text, unique=True, nullable=False)
    title = Column(Text)
    author = Column(Text)
    description = Column(Text)
    category = Column(Text)

    priority = Column(Integer, default=3)
    is_active = Column(Boolean, default=True)

    last_scanned_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    episodes = relationship(
        "RSSEpisode",
        back_populates="feed",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "feed_url": self.feed_url,
            "title": self.title,
            "author": self.author,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "is_active": self.is_active,
            "last_scanned_at": self.last_scanned_at.isoformat()
            if self.last_scanned_at
            else None,
        }
    
class RSSEpisode(Base):
    __tablename__ = "rss_episodes"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    guid = Column(Text, unique=True, nullable=False)

    feed_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rss_feeds.id", ondelete="CASCADE"),
    )

    title = Column(Text)
    description = Column(Text)

    audio_url = Column(Text)

    episode_number = Column(Integer)

    published_at = Column(DateTime(timezone=True))

    duration = Column(Integer)

    status = Column(Text, default="pending")

    classification_confidence = Column(Float)

    transcript_id = Column(UUID(as_uuid=True))

    discovered_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )

    classified_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    feed = relationship("RSSFeed", back_populates="episodes")

    def to_dict(self, include_feed=False):
        d = {
            "id": str(self.id),
            "guid": self.guid,
            "feed_id": str(self.feed_id) if self.feed_id else None,
            "title": self.title,
            "description": self.description,
            "audio_url": self.audio_url,
            "episode_number": self.episode_number,
            "published_at": self.published_at.isoformat()
            if self.published_at
            else None,
            "duration": self.duration,
            "status": self.status,
            "classification_confidence": self.classification_confidence,
            "transcript_id": str(self.transcript_id)
            if self.transcript_id
            else None,
            "discovered_at": self.discovered_at.isoformat()
            if self.discovered_at
            else None,
            "classified_at": self.classified_at.isoformat()
            if self.classified_at
            else None,
        }

        if include_feed and self.feed:
            d["rss_feed"] = {
                "title": self.feed.title,
                "author": self.feed.author,
            }
        else:
            d["rss_feed"] = None

        return d
