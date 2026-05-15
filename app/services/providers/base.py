from abc import ABC, abstractmethod
from typing import Dict, Any

from app.data_writer import DataWriter
from app.transcript import Transcript

class BaseTranscriptionService(ABC):
    @classmethod
    @abstractmethod
    def from_config(cls, config: Dict[str, Any], metadata_writer: DataWriter) -> "BaseTranscriptionService":
        """Instantiate the transcription service from a configuration dictionary."""
        pass

    @abstractmethod
    def transcribe(self, transcript: Transcript) -> None:
        """Perform the transcription on the given transcript object."""
        pass

    @abstractmethod
    def finalize_transcript(self, transcript: Transcript) -> None:
        """Finalize the transcription formatting and output files."""
        pass
