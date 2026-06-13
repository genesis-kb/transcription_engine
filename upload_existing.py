import os
import sys
from pathlib import Path

# Add the app to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import get_session
from app.models import AudioEpisode, AudioPlaylist
from app.services.audiobook.storage import upload_to_supabase
from app.logging import get_logger

logger = get_logger()

def main():
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_KEY"):
        logger.error("Please set SUPABASE_URL and SUPABASE_KEY environment variables.")
        return

    with get_session() as session:
        # Find all episodes that have local paths
        episodes = session.query(AudioEpisode).filter(AudioEpisode.audio_url.like('/home/%')).all()
        
        if not episodes:
            logger.info("No episodes with local audio paths found.")
            return
            
        logger.info(f"Found {len(episodes)} episodes to migrate to Supabase.")
        
        for ep in episodes:
            local_path = Path(ep.audio_url)
            if not local_path.exists():
                logger.warning(f"File not found: {local_path}. Skipping.")
                continue
                
            playlist = session.query(AudioPlaylist).filter_by(id=ep.playlist_id).first()
            playlist_title = playlist.title if playlist else "Unknown"
            
            safe_ep_title = "".join(c if c.isalnum() or c in " _-" else "" for c in ep.title).replace(" ", "_")
            ext = local_path.suffix
            destination_path = f"{playlist_title}/{safe_ep_title}{ext}"
            
            logger.info(f"Uploading {ep.title} to {destination_path}...")
            public_url = upload_to_supabase(local_path, "audiobooks", destination_path)
            
            if public_url:
                ep.audio_url = public_url
                session.commit()
                logger.info(f"Updated DB for {ep.title} -> {public_url}")
            else:
                logger.error(f"Failed to upload {ep.title}")

if __name__ == "__main__":
    main()
