import os
import sys
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT))

from dotenv import load_dotenv
from app.database import init_db

# Ensure env vars are loaded for standalone execution from the project root
load_dotenv(dotenv_path=REPO_ROOT / ".env")

def main():
    print("------------------------------------------")
    print("  Bitcoin Transcription Engine - DB Init")
    print("------------------------------------------")
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL not found in environment or .env file.")
        sys.exit(1)
        
    print(f"Connecting to: {database_url.split('@')[-1]}")
    print("Initializing database schema...")
    
    try:
        success = init_db()
        if success:
            print("\n[OK] Success: Database initialized successfully.")
            print("  Tables created or already exist.")
        else:
            print("\n[ERROR] Fail: Database initialization failed (check logs).")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
