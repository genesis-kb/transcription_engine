"""SQLAlchemy ORM models for the transcription engine database.

New multi-source, platform-agnostic schema (v2).
Tables: taxonomies, content_sources, content_items, speakers,
        content_item_speakers, transcripts, summaries,
        external_publications, pipeline_runs.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# =========================================================================
# 1. TAXONOMIES — The Filter Engine
# =========================================================================


class Taxonomy(Base):
    """Hierarchical taxonomy for conferences, topics, tags, series."""

    __tablename__ = "taxonomies"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    type = Column(Text, nullable=False)  # 'conference', 'topic', 'tag', 'series'
    name = Column(Text, nullable=False)
    slug = Column(Text, nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("taxonomies.id"))
    meta = Column("metadata", JSONB, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    parent = relationship("Taxonomy", remote_side=[id], backref="children")

    __table_args__ = (
        UniqueConstraint("type", "slug", name="uq_taxonomies_type_slug"),
        Index("idx_taxonomies_parent", "parent_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "type": self.type,
            "name": self.name,
            "slug": self.slug,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "metadata": self.meta or {},
            "created_at": self.created_at.isoformat()
            if self.created_at
            else None,
        }


# =========================================================================
# 2. CONTENT SOURCES — The Registry
# =========================================================================


class ContentSource(Base):
    """Where content comes from: YouTube channels, scrapers, RSS, manual."""

    __tablename__ = "content_sources"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name = Column(Text, nullable=False)
    slug = Column(Text, unique=True, nullable=False)
    source_type = Column(Text, nullable=False)  # 'youtube', 'scraper', 'rss', 'manual'
    base_url = Column(Text)
    config = Column(JSONB, server_default=text("'{}'::jsonb"))
    is_active = Column(Boolean, server_default=text("true"))
    last_run_status = Column(Text)
    last_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_runs.id", use_alter=True, name="fk_sources_last_run"),
    )
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    items = relationship(
        "ContentItem", back_populates="source", cascade="all, delete-orphan"
    )
    pipeline_runs = relationship(
        "PipelineRun",
        back_populates="source",
        foreign_keys="PipelineRun.source_id",
    )

    __table_args__ = (
        Index("idx_sources_type", "source_type"),
        Index(
            "idx_sources_active",
            "is_active",
            postgresql_where=text("is_active = true"),
        ),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "source_type": self.source_type,
            "base_url": self.base_url,
            "config": self.config or {},
            "is_active": self.is_active,
            "last_run_status": self.last_run_status,
            "last_run_id": str(self.last_run_id) if self.last_run_id else None,
            "created_at": self.created_at.isoformat()
            if self.created_at
            else None,
        }


# =========================================================================
# 3. CONTENT ITEMS — The Hub
# =========================================================================


class ContentItem(Base):
    """Every piece of discovered content: video, article, email, post."""

    __tablename__ = "content_items"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content_sources.id"),
        nullable=False,
    )
    external_id = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    content_type = Column(Text, nullable=False)  # 'video', 'audio', 'text'
    url = Column(Text, unique=True)
    published_at = Column(DateTime(timezone=True))
    event_date = Column(Date)
    event_id = Column(UUID(as_uuid=True), ForeignKey("taxonomies.id"))
    status = Column(
        Text, nullable=False, server_default=text("'discovered'")
    )
    technical_score = Column(Integer)  # 1-5
    source_metadata = Column(JSONB, server_default=text("'{}'::jsonb"))
    discovered_at = Column(
        DateTime(timezone=True), server_default=text("now()")
    )

    source = relationship("ContentSource", back_populates="items")
    event = relationship("Taxonomy")
    transcripts = relationship(
        "Transcript",
        back_populates="content_item",
        cascade="all, delete-orphan",
    )
    speaker_links = relationship(
        "ContentItemSpeaker",
        back_populates="content_item",
        cascade="all, delete-orphan",
    )
    publications = relationship(
        "ExternalPublication",
        back_populates="content_item",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "external_id",
            name="uq_content_items_source_external",
        ),
        CheckConstraint(
            "technical_score BETWEEN 1 AND 5",
            name="ck_technical_score_range",
        ),
        Index("idx_items_source", "source_id"),
        Index("idx_items_event", "event_id"),
        Index("idx_items_status", "status"),
        Index("idx_items_type", "content_type"),
        Index("idx_items_published", text("published_at DESC")),
        Index(
            "idx_items_technical",
            "technical_score",
            postgresql_where=text("technical_score >= 4"),
        ),
    )

    def to_dict(self, include_source=False):
        d = {
            "id": str(self.id),
            "source_id": str(self.source_id) if self.source_id else None,
            "external_id": self.external_id,
            "title": self.title,
            "description": self.description,
            "content_type": self.content_type,
            "url": self.url,
            "published_at": self.published_at.isoformat()
            if self.published_at
            else None,
            "event_date": self.event_date.isoformat()
            if self.event_date
            else None,
            "event_id": str(self.event_id) if self.event_id else None,
            "status": self.status,
            "technical_score": self.technical_score,
            "source_metadata": self.source_metadata or {},
            "discovered_at": self.discovered_at.isoformat()
            if self.discovered_at
            else None,
        }
        if include_source and self.source:
            d["content_source"] = {
                "name": self.source.name,
                "source_type": self.source.source_type,
                "slug": self.source.slug,
            }
        else:
            d["content_source"] = None
        return d


# =========================================================================
# 4. SPEAKERS & ATTRIBUTION
# =========================================================================


class Speaker(Base):
    """Normalised speaker/author profiles for cross-referencing."""

    __tablename__ = "speakers"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name = Column(Text, nullable=False)
    slug = Column(Text, unique=True, nullable=False)
    aliases = Column(ARRAY(Text), server_default=text("'{}'"))
    bio = Column(Text)
    thumbnail = Column(Text)
    links = Column(JSONB, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    content_item_links = relationship(
        "ContentItemSpeaker", back_populates="speaker"
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "aliases": self.aliases or [],
            "bio": self.bio,
            "thumbnail": self.thumbnail,
            "links": self.links or {},
            "created_at": self.created_at.isoformat()
            if self.created_at
            else None,
        }


class ContentItemSpeaker(Base):
    """M:N junction linking speakers to content items."""

    __tablename__ = "content_item_speakers"

    content_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    speaker_id = Column(
        UUID(as_uuid=True),
        ForeignKey("speakers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role = Column(Text, server_default=text("'speaker'"))

    content_item = relationship("ContentItem", back_populates="speaker_links")
    speaker = relationship("Speaker", back_populates="content_item_links")

    __table_args__ = (
        Index("idx_cis_speaker", "speaker_id"),
    )


# =========================================================================
# 5. TRANSCRIPTS — Version Controlled
# =========================================================================


class Transcript(Base):
    """STT output with version control. is_current=true marks the active version."""

    __tablename__ = "transcripts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    content_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_current = Column(Boolean, server_default=text("false"))
    version = Column(Integer, server_default=text("1"))
    raw_text = Column(Text)
    corrected_text = Column(Text)
    stt_model = Column(Text)
    correction_model = Column(Text)
    duration_seconds = Column(Integer)
    word_count = Column(Integer)
    chapters = Column(JSONB, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    content_item = relationship("ContentItem", back_populates="transcripts")
    summaries = relationship(
        "Summary",
        back_populates="transcript",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "idx_single_active_transcript",
            "content_item_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "content_item_id": str(self.content_item_id)
            if self.content_item_id
            else None,
            "is_current": self.is_current,
            "version": self.version,
            "raw_text": self.raw_text,
            "corrected_text": self.corrected_text,
            "stt_model": self.stt_model,
            "correction_model": self.correction_model,
            "duration_seconds": self.duration_seconds,
            "word_count": self.word_count,
            "chapters": self.chapters or [],
            "created_at": self.created_at.isoformat()
            if self.created_at
            else None,
        }


# =========================================================================
# 6. SUMMARIES
# =========================================================================


class Summary(Base):
    """LLM-generated summaries in multiple formats per transcript."""

    __tablename__ = "summaries"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    transcript_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary_type = Column(Text, nullable=False)  # 'tldr', 'technical', 'newsletter'
    content = Column(Text, nullable=False)
    model_used = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    transcript = relationship("Transcript", back_populates="summaries")

    __table_args__ = (
        Index("idx_summaries_type", "summary_type"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "transcript_id": str(self.transcript_id)
            if self.transcript_id
            else None,
            "summary_type": self.summary_type,
            "content": self.content,
            "model_used": self.model_used,
            "created_at": self.created_at.isoformat()
            if self.created_at
            else None,
        }


# =========================================================================
# 7. EXTERNAL PUBLICATIONS — Cross-platform distribution
# =========================================================================


class ExternalPublication(Base):
    """Tracks content published to external platforms (YT comments, tweets, etc.)."""

    __tablename__ = "external_publications"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    content_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform = Column(Text, nullable=False)  # 'youtube', 'twitter', etc.
    external_pub_id = Column(Text)  # YT comment thread ID, tweet ID, etc.
    pub_url = Column(Text)
    status = Column(Text, server_default=text("'pending'"))
    last_error = Column(Text)
    published_at = Column(DateTime(timezone=True))

    content_item = relationship("ContentItem", back_populates="publications")

    def to_dict(self):
        return {
            "id": str(self.id),
            "content_item_id": str(self.content_item_id)
            if self.content_item_id
            else None,
            "platform": self.platform,
            "external_pub_id": self.external_pub_id,
            "pub_url": self.pub_url,
            "status": self.status,
            "last_error": self.last_error,
            "published_at": self.published_at.isoformat()
            if self.published_at
            else None,
        }


# =========================================================================
# 8. PIPELINE RUNS — Audit log
# =========================================================================


class PipelineRun(Base):
    """Macro-level audit log for pipeline executions."""

    __tablename__ = "pipeline_runs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_id = Column(
        UUID(as_uuid=True), ForeignKey("content_sources.id")
    )
    started_at = Column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at = Column(DateTime(timezone=True))
    status = Column(Text)  # 'success', 'failed', 'partial'

    source = relationship(
        "ContentSource",
        back_populates="pipeline_runs",
        foreign_keys=[source_id],
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "source_id": str(self.source_id) if self.source_id else None,
            "started_at": self.started_at.isoformat()
            if self.started_at
            else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "status": self.status,
        }
