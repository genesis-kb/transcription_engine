from app.exceptions.base import NonRetryableError, RetryableError, TranscriptionEngineError


class ASRProviderError(TranscriptionEngineError):
    """Base for all ASR provider errors."""
    pass


class UnsupportedASRProviderError(NonRetryableError):
    def __init__(self, provider):
        super().__init__(f"Unsupported ASR provider: {provider}")


class TranscriptionOutputMissingError(NonRetryableError):
    def __init__(self, provider):
        super().__init__(f"No '{provider}_output' found in JSON")


class DeepgramTranscriptionError(ASRProviderError, RetryableError):
    def __init__(self, message):
        super().__init__(f"(deepgram) Error transcribing audio to text: {message}")


class DeepgramOutputParsingError(ASRProviderError, NonRetryableError):
    def __init__(self, message):
        super().__init__(f"(deepgram) Error parsing output: {message}")


class WhisperLoadError(ASRProviderError, NonRetryableError):
    def __init__(self, message="Whisper is not installed. Install with 'pip install .[whisper]'"):
        super().__init__(message)


class WhisperTranscriptionError(ASRProviderError, RetryableError):
    def __init__(self, model, message):
        super().__init__(f"(whisper,{model}) Error transcribing audio to text: {message}")


class SmallestAITranscriptionError(ASRProviderError, RetryableError):
    def __init__(self, message):
        super().__init__(f"(smallestai) Error transcribing audio to text: {message}")


class SmallestAITimeoutError(ASRProviderError, RetryableError):
    def __init__(self, message="(smallestai) Request timed out. Audio may be too long — try enabling chunked transcription."):
        super().__init__(message)
