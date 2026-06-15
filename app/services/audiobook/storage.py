import os
import mimetypes
import requests
import urllib.parse
from pathlib import Path
from typing import Optional
from app.logging import get_logger

logger = get_logger()

def upload_to_supabase(file_path: Path, bucket_name: str, destination_path: str) -> Optional[str]:
    """Uploads a file to Supabase storage using the REST API and returns the public URL."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.warning("SUPABASE_URL or SUPABASE_KEY not set. Cannot upload to Supabase.")
        return None
        
    safe_destination = urllib.parse.quote(destination_path)
    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket_name}/{safe_destination}"
    mime_type, _ = mimetypes.guess_type(str(file_path))
    
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
        "Content-Type": mime_type or "audio/mpeg",
        "x-upsert": "true"
    }
    
    try:
        with open(file_path, "rb") as f:
            response = requests.post(url, headers=headers, data=f, timeout=30)
            response.raise_for_status()
            
        public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket_name}/{safe_destination}"
        logger.info(f"Successfully uploaded to Supabase: {public_url}")
        return public_url
    except Exception as e:
        logger.error(f"Failed to upload to Supabase: {e}")
        return None
