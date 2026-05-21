from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from app.database import get_session, is_db_configured
from app.logging import get_logger
from app.models import ContentItem, ContentItemSpeaker, ContentSource, PipelineRun, Speaker, Summary, Taxonomy, Transcript

logger = get_logger()

# Global singleton instance
_database_service: Optional["DatabaseService"] = None


class DatabaseService:
    """Service for interacting with the PostgreSQL database via SQLAlchemy."""

    def __init__(self):
        self._is_available = is_db_configured()
        if self._is_available:
            logger.info("Database service initialized successfully.")
        else:
            logger.debug(
                "Database not configured. Database integration disabled."
            )

    @property
    def is_available(self) -> bool:
        return self._is_available

    # =========================================================================
    # Transcripts
    # =========================================================================

    def save_from_transcript_object(self, transcript) -> Optional[dict]:
        if not self.is_available:
            return None
            
        from sqlalchemy.exc import IntegrityError
        import time
        
        for attempt in range(3):
            try:
                with get_session() as session:
                    source = transcript.source
                    raw_media_url = source.source_file
                    if isinstance(raw_media_url, str):
                        raw_media_url = raw_media_url.strip()
                    media_url = raw_media_url or None

                    video_id = None
                    media_url_for_parsing = media_url or ""
                    if "v=" in media_url_for_parsing:
                        video_id = media_url_for_parsing.split("v=")[-1].split("&")[0]
                    elif "youtu.be/" in media_url_for_parsing:
                        video_id = media_url_for_parsing.split("youtu.be/")[-1].split("?")[0]

                    import uuid
                    
                    content_source = None
                    if hasattr(source, "loc") and source.loc:
                        content_source = session.query(ContentSource).filter_by(slug=source.loc).first()
                        
                    content_item = None
                    if video_id:
                        query = session.query(ContentItem).filter_by(external_id=video_id)
                        if content_source:
                            query = query.filter_by(source_id=content_source.id)
                        content_item = query.first()
                    
                    if not content_item:
                        if content_source:
                            target_source_id = content_source.id
                        else:
                            # Find or create manual source
                            manual_source = session.query(ContentSource).filter_by(slug='manual-imports').first()
                            if not manual_source:
                                manual_source = ContentSource(
                                    name='Manual Imports',
                                    slug='manual-imports',
                                    source_type='manual',
                                    is_active=True
                                )
                                session.add(manual_source)
                                session.flush()
                            target_source_id = manual_source.id

                        ext_id = video_id if video_id else f"manual-{uuid.uuid4().hex[:12]}"
                        
                        content_item = session.query(ContentItem).filter_by(source_id=target_source_id, external_id=ext_id).first()
                        if not content_item:
                            content_item = ContentItem(
                                source_id=target_source_id,
                                external_id=ext_id,
                                title=source.title or 'Unknown',
                                content_type='video',
                                url=media_url,
                                status='transcribed'
                            )
                            session.add(content_item)
                            session.flush()
                    else:
                        content_item.status = 'transcribed'

                    # Lock existing transcripts to prevent race condition
                    existing_transcripts = session.query(Transcript).filter_by(content_item_id=content_item.id).with_for_update().all()
                    
                    next_version = 1
                    for existing_t in existing_transcripts:
                        if existing_t.version >= next_version:
                            next_version = existing_t.version + 1
                        if existing_t.is_current:
                            existing_t.is_current = False

                    # Add transcript
                    t = Transcript(
                        content_item_id=content_item.id,
                        is_current=True,
                        version=next_version,
                        raw_text=transcript.outputs.get("raw", ""),
                        corrected_text=transcript.outputs.get("corrected_text", "")
                    )
                    session.add(t)
                    session.flush()
                    
                    # Add summary
                    summary_text = transcript.summary if hasattr(transcript, "summary") else None
                    if summary_text:
                        s = Summary(
                            transcript_id=t.id,
                            summary_type='tldr',
                            content=summary_text
                        )
                        session.add(s)

                    # Add speakers
                    if source.speakers:
                        import re
                        for spk_name in source.speakers:
                            spk_slug = re.sub(r"[^\w\s-]", "", spk_name.lower().strip())
                            spk_slug = re.sub(r"[-\s]+", "-", spk_slug).strip("-") or "unknown"
                            spk = session.query(Speaker).filter_by(slug=spk_slug).first()
                            if not spk:
                                spk = Speaker(name=spk_name, slug=spk_slug)
                                session.add(spk)
                                session.flush()
                            
                            cis = session.query(ContentItemSpeaker).filter_by(content_item_id=content_item.id, speaker_id=spk.id).first()
                            if not cis:
                                cis = ContentItemSpeaker(content_item_id=content_item.id, speaker_id=spk.id, role='speaker')
                                session.add(cis)

                    session.commit()
                    return t.to_dict()
            except IntegrityError:
                if attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                logger.error("Failed to save transcript object due to IntegrityError after retries.")
                return None
            except Exception as e:
                logger.error(f"Failed to save transcript object: {e}")
                return None
        return None

    def get_all_transcripts(self, limit: int = 100, offset: int = 0) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(Transcript)
                    .order_by(desc(Transcript.created_at))
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [obj.to_dict() for obj in objs]
        except Exception as e:
            logger.error(f"Failed to get all transcripts: {e}")
            return []

    def get_transcript_by_id(self, transcript_id: str) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = (
                    session.query(Transcript)
                    .filter_by(id=transcript_id)
                    .first()
                )
                return obj.to_dict() if obj else None
        except Exception as e:
            logger.error(f"Failed to get transcript {transcript_id}: {e}")
            return None

    def get_corrected_transcripts(
        self, limit: int = 100, offset: int = 0
    ) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(Transcript)
                    .filter(Transcript.corrected_text.isnot(None))
                    .order_by(desc(Transcript.created_at))
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [obj.to_dict() for obj in objs]
        except Exception as e:
            logger.error(f"Failed to get corrected transcripts: {e}")
            return []

    def get_summaries(self, limit: int = 100, offset: int = 0) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(Summary)
                    .order_by(desc(Summary.created_at))
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [obj.to_dict() for obj in objs]
        except Exception as e:
            logger.error(f"Failed to get summaries: {e}")
            return []

    # =========================================================================
    # Content Sources
    # =========================================================================

    def get_active_sources(self, source_type: Optional[str] = None) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                query = session.query(ContentSource).filter_by(is_active=True)
                if source_type:
                    query = query.filter_by(source_type=source_type)
                objs = query.all()
                return [obj.to_dict() for obj in objs]
        except Exception as e:
            logger.error(f"Failed to get active sources: {e}")
            return []

    def get_source_by_id(self, source_id: str) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = (
                    session.query(ContentSource)
                    .filter_by(id=source_id)
                    .first()
                )
                return obj.to_dict() if obj else None
        except Exception as e:
            logger.error(f"Failed to get source {source_id}: {e}")
            return None

    def list_sources(self) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(ContentSource)
                    .order_by(ContentSource.name)
                    .all()
                )
                return [obj.to_dict() for obj in objs]
        except Exception as e:
            logger.error(f"Failed to list sources: {e}")
            return []

    def add_source(self, source_data: dict) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = ContentSource(**source_data)
                session.add(obj)
                session.commit()
                return obj.to_dict()
        except Exception as e:
            logger.error(f"Failed to add source: {e}")
            return None

    def update_source(self, source_id: str, updates: dict) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = (
                    session.query(ContentSource)
                    .filter_by(id=source_id)
                    .first()
                )
                if not obj:
                    return None
                for key, value in updates.items():
                    setattr(obj, key, value)
                session.commit()
                return obj.to_dict()
        except Exception as e:
            logger.error(f"Failed to update source {source_id}: {e}")
            return None

    def delete_source(self, source_id: str) -> bool:
        if not self.is_available:
            return False
        try:
            with get_session() as session:
                obj = (
                    session.query(ContentSource)
                    .filter_by(id=source_id)
                    .first()
                )
                if not obj:
                    return False
                session.delete(obj)
                session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to delete source {source_id}: {e}")
            return False

    def update_source_last_scanned(self, source_id: str):
        if not self.is_available:
            return
        try:
            with get_session() as session:
                obj = (
                    session.query(ContentSource)
                    .filter_by(id=source_id)
                    .first()
                )
                if obj:
                    # using config jsonb to store last_scanned_at
                    config = dict(obj.config or {})
                    config["last_scanned_at"] = datetime.now(timezone.utc).isoformat()
                    obj.config = config
                    session.commit()
        except Exception as e:
            logger.error(
                f"Failed to update scan time for source {source_id}: {e}"
            )

    # =========================================================================
    # Content Items
    # =========================================================================

    def insert_content_item(self, item_data: dict) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = ContentItem(**item_data)
                session.add(obj)
                session.commit()
                return obj.to_dict()
        except Exception as e:
            logger.error(
                f"Failed to insert item {item_data.get('external_id')}: {e}"
            )
            return None

    def get_existing_item_external_ids(self, source_id: str, external_ids: list[str]) -> set:
        if not self.is_available or not external_ids:
            return set()
        try:
            with get_session() as session:
                rows = (
                    session.query(ContentItem.external_id)
                    .filter(ContentItem.source_id == source_id)
                    .filter(ContentItem.external_id.in_(external_ids))
                    .all()
                )
                return {row[0] for row in rows}
        except Exception as e:
            logger.error(f"Failed to check existing items: {e}")
            return set()

    def get_items_by_status(self, status: str, limit: int = 100) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(ContentItem)
                    .options(joinedload(ContentItem.source))
                    .filter(ContentItem.status == status)
                    .order_by(desc(ContentItem.discovered_at))
                    .limit(limit)
                    .all()
                )
                return [obj.to_dict(include_source=True) for obj in objs]
        except Exception as e:
            logger.error(f"Failed to get items by status '{status}': {e}")
            return []

    def list_content_items(
        self,
        status: Optional[str] = None,
        is_technical: Optional[bool] = None,
        source_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                query = (
                    session.query(ContentItem)
                    .options(joinedload(ContentItem.source))
                    .order_by(desc(ContentItem.discovered_at))
                )
                if status:
                    query = query.filter(ContentItem.status == status)
                if is_technical is True:
                    query = query.filter(
                        ContentItem.technical_score >= 4
                    )
                elif is_technical is False:
                    query = query.filter(
                        ContentItem.technical_score < 4
                    )
                if source_id:
                    query = query.filter(ContentItem.source_id == source_id)
                objs = query.offset(offset).limit(limit).all()
                return [obj.to_dict(include_source=True) for obj in objs]
        except Exception as e:
            logger.error(f"Failed to list content items: {e}")
            return []

    def get_item_by_id(self, item_id: str) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = (
                    session.query(ContentItem)
                    .options(joinedload(ContentItem.source))
                    .filter_by(id=item_id)
                    .first()
                )
                return obj.to_dict(include_source=True) if obj else None
        except Exception as e:
            logger.error(f"Failed to get item {item_id}: {e}")
            return None

    def update_content_item(
        self, item_id: str, updates: dict
    ) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = session.query(ContentItem).filter_by(id=item_id).first()
                if not obj:
                    return None
                for key, value in updates.items():
                    setattr(obj, key, value)
                session.commit()
                return obj.to_dict()
        except Exception as e:
            logger.error(f"Failed to update item {item_id}: {e}")
            return None

    # =========================================================================
    # Pipeline Runs
    # =========================================================================

    def create_pipeline_run(self, **kwargs) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = PipelineRun(**kwargs)
                session.add(obj)
                session.commit()
                return obj.to_dict()
        except Exception as e:
            logger.error(f"Failed to create pipeline run: {e}")
            return None

    def complete_pipeline_run(self, run_id: str, **kwargs) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = session.query(PipelineRun).filter_by(id=run_id).first()
                if not obj:
                    return None
                for key, value in kwargs.items():
                    setattr(obj, key, value)
                
                # Also update last_run_status and last_run_id on source
                if obj.source_id:
                    source = session.query(ContentSource).filter_by(id=obj.source_id).first()
                    if source:
                        source.last_run_id = obj.id
                        source.last_run_status = obj.status
                
                session.commit()
                return obj.to_dict()
        except Exception as e:
            logger.error(f"Failed to complete pipeline run {run_id}: {e}")
            return None

    def list_pipeline_runs(self, limit: int = 50) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(PipelineRun)
                    .options(joinedload(PipelineRun.source))
                    .order_by(desc(PipelineRun.started_at))
                    .limit(limit)
                    .all()
                )
                res = []
                for obj in objs:
                    d = obj.to_dict()
                    if obj.source:
                        d['content_source'] = {'name': obj.source.name, 'slug': obj.source.slug}
                    res.append(d)
                return res
        except Exception as e:
            logger.error(f"Failed to list pipeline runs: {e}")
            return []


def get_database_service() -> DatabaseService:
    """Get the singleton DatabaseService instance."""
    global _database_service
    if _database_service is None:
        _database_service = DatabaseService()
    return _database_service
