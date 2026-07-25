#!/usr/bin/env python3
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

# Fix python path if run from scripts/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.config import settings

def main():
    client_secrets_file = settings.YOUTUBE_CLIENT_SECRETS_FILE
    token_file = settings.YOUTUBE_OAUTH_TOKEN_FILE
    
    if not os.path.exists(client_secrets_file):
        print(f"Error: Client secrets file not found at {client_secrets_file}")
        print("Please download your OAuth client secrets from Google Cloud Console and place them there.")
        return

    SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

    print("Starting interactive OAuth flow...")
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    
    # Run a local server without automatically opening the browser
    # This prints a URL to the terminal which the user can visit on their local machine
    creds = flow.run_local_server(port=8080, open_browser=False)

    with open(token_file, "w") as f:
        f.write(creds.to_json())
    
    print(f"Success! Token saved to {token_file}")

if __name__ == "__main__":
    main()
