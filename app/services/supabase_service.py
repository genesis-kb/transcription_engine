"""
Supabase Service for persisting transcripts to a Supabase database.
"""
import os
from typing import Optional
from app.config import settings
from app.logging import get_logger

logger = get_logger()

# Global singleton instance
_supabase_service: Optional["SupabaseService"] = None


class SupabaseService:
    """Service for interacting with Supabase database."""
    
    def __init__(self):
        self._client = None
        self._is_available = False
        self._init_client()
    
    def _init_client(self):
        """Initialize the Supabase client if credentials are available."""
        url = settings.SUPABASE_URL
        key = settings.SUPABASE_KEY
        
        if not url or not key:
            logger.debug("Supabase credentials not configured. Supabase integration disabled.")
            return
        
        try:
            from supabase import create_client, Client
            self._client: Client = create_client(url, key)
            self._is_available = True
            logger.info("Supabase client initialized successfully.")
        except ImportError:
            logger.warning("supabase-py not installed. Run: pip install supabase")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if Supabase service is available and configured."""
        return self._is_available
    
    @property
    def client(self):
        """Get the Supabase client."""
        return self._client
    
    def save_transcript(self, transcript_data: dict) -> Optional[dict]:
        """
        Save a transcript to Supabase.
        
        Args:
            transcript_data: Dictionary containing transcript data
            
        Returns:
            The inserted record or None if failed
        """
        if not self.is_available:
            logger.debug("Supabase not available, skipping save.")
            return None
        
        try:
            result = self._client.table("transcripts").insert(transcript_data).execute()
            logger.info(f"Transcript saved to Supabase: {transcript_data.get('title', 'Unknown')}")
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to save transcript to Supabase: {e}")
            return None
    
    def save_from_transcript_object(self, transcript) -> Optional[dict]:
        """
        Save a Transcript object to Supabase.
        
        Args:
            transcript: Transcript object with source metadata
            
        Returns:
            The inserted record or None if failed
        """
        if not self.is_available:
            return None
        
        try:
            source = transcript.source
            transcript_data = {
                "title": source.title,
                "loc": source.loc,
                "event_date": str(source.date) if source.date else None,
                "speakers": source.speakers if source.speakers else [],
                "tags": source.tags if source.tags else [],
                "categories": source.category if source.category else [],
                "raw_text": transcript.outputs.get("raw", ""),
                "corrected_text": transcript.outputs.get("corrected_text", ""),
                "summary": transcript.summary if hasattr(transcript, "summary") else None,
                "media_url": source.source_file,
                "status": transcript.status,
            }
            return self.save_transcript(transcript_data)
        except Exception as e:
            logger.error(f"Failed to save transcript object to Supabase: {e}")
            return None
    
    def get_transcript(self, title: str, loc: str) -> Optional[dict]:
        """
        Get a transcript from Supabase by title and location.
        
        Args:
            title: The transcript title
            loc: The location/category
            
        Returns:
            The transcript record or None if not found
        """
        if not self.is_available:
            return None
        
        try:
            result = (
                self._client.table("transcripts")
                .select("*")
                .eq("title", title)
                .eq("loc", loc)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get transcript from Supabase: {e}")
            return None
    
    def list_transcripts(self, loc: Optional[str] = None, limit: int = 100) -> list:
        """
        List transcripts from Supabase.
        
        Args:
            loc: Optional location filter
            limit: Maximum number of results
            
        Returns:
            List of transcript records
        """
        if not self.is_available:
            return []
        
        try:
            query = self._client.table("transcripts").select("*").limit(limit)
            if loc:
                query = query.eq("loc", loc)
            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to list transcripts from Supabase: {e}")
            return []


def get_supabase_service() -> SupabaseService:
    """
    Get the singleton SupabaseService instance.
    
    Returns:
        SupabaseService instance
    """
    global _supabase_service
    if _supabase_service is None:
        _supabase_service = SupabaseService()
    return _supabase_service
