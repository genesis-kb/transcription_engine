import os
import sys
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Add project root to path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import _get_engine

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def add_indexes():
    engine = _get_engine()
    if not engine:
        logger.error("Could not get database engine. Check DATABASE_URL.")
        return

    logger.info("Adding performance and Full-Text Search (FTS) indexes to database...")

    index_sqls = [
        # content_sources
        "CREATE INDEX IF NOT EXISTS idx_sources_type ON content_sources(source_type);",
        "CREATE INDEX IF NOT EXISTS idx_sources_active ON content_sources(is_active) WHERE is_active = true;",
        
        # content_items
        "CREATE INDEX IF NOT EXISTS idx_items_source ON content_items(source_id);",
        "CREATE INDEX IF NOT EXISTS idx_items_status ON content_items(status);",
        "CREATE INDEX IF NOT EXISTS idx_items_type ON content_items(content_type);",
        "CREATE INDEX IF NOT EXISTS idx_items_published ON content_items(published_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_items_technical ON content_items(technical_score) WHERE technical_score >= 4;",
        
        # content_item_speakers
        "CREATE INDEX IF NOT EXISTS idx_cis_speaker ON content_item_speakers(speaker_id);",
        
        # transcripts FTS (GIN index on tsvector)
        """
        CREATE INDEX IF NOT EXISTS idx_transcripts_fts 
        ON transcripts USING GIN(to_tsvector('english', COALESCE(corrected_text, raw_text, '')));
        """,
        
        # summaries FTS (GIN index on tsvector)
        """
        CREATE INDEX IF NOT EXISTS idx_summaries_fts 
        ON summaries USING GIN(to_tsvector('english', COALESCE(content, '')));
        """
    ]

    with engine.connect() as conn:
        with conn.begin():
            # Postgres GIN indexes require the pg_trgm extension for some advanced text operations,
            # though to_tsvector doesn't strictly need it, it's good to have.
            conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pg_trgm";'))
            
            for sql in index_sqls:
                logger.info(f"Executing: {sql.strip().split(chr(10))[0]}...")
                conn.execute(text(sql))

    logger.info("All indexes created successfully!")

if __name__ == "__main__":
    try:
        add_indexes()
    except Exception as e:
        logger.error(f"Failed to add indexes: {e}")
        import traceback
        traceback.print_exc()
