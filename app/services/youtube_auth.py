"""YouTube OAuth 2.0 authentication for comment posting.

Posting comments to YouTube requires OAuth 2.0 (not just an API key).
This module handles token loading, refreshing, and the initial
interactive authorization flow.
"""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import settings
from app.logging import get_logger


logger = get_logger()

# This scope is required for posting/deleting comments
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


def get_authenticated_youtube_service():
    """Return an authenticated YouTube API service for comment operations.

    Loads credentials from the stored token file. If the token is expired,
    it auto-refreshes. If no token exists, raises an error directing the
    user to run the setup script.

    Returns:
        googleapiclient.discovery.Resource: Authenticated YouTube service.

    Raises:
        RuntimeError: If no valid credentials are available.
    """
    token_file = settings.YOUTUBE_OAUTH_TOKEN_FILE
    client_secrets_file = settings.YOUTUBE_CLIENT_SECRETS_FILE
    creds = None

    # Load existing token
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            logger.debug("YouTube OAuth token loaded from file.")
        except Exception as e:
            logger.warning(f"Failed to load YouTube OAuth token: {e}")
            creds = None

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds, token_file)
            logger.info("YouTube OAuth token refreshed successfully.")
        except Exception as e:
            logger.error(f"Failed to refresh YouTube OAuth token: {e}")
            creds = None

    # If still no valid creds, try interactive flow (only works with a TTY)
    if not creds or not creds.valid:
        raise RuntimeError(
            f"YouTube OAuth token missing or invalid. "
            f"Ensure client secrets exist at '{client_secrets_file}' "
            f"and run 'python scripts/setup_youtube_oauth.py' manually "
            f"to authorize the application."
        )

    return build("youtube", "v3", credentials=creds)


def _save_token(creds: Credentials, token_file: str):
    """Persist credentials to disk for future use."""
    with open(token_file, "w") as f:
        f.write(creds.to_json())
    logger.debug(f"YouTube OAuth token saved to {token_file}.")
