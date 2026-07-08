# Proxy module — re-exports from the modularized audiobook package.
from .audiobook.pipeline import AudiobookService, AudioPipeline
from .audiobook.curator import AudiobookCurator
from .audiobook.playlist_service import PlaylistService

__all__ = [
    "AudiobookService",
    "AudioPipeline",
    "AudiobookCurator",
    "PlaylistService",
]
