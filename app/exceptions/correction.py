from app.exceptions.base import NonRetryableError, RetryableError, TranscriptionEngineError


class CorrectionError(TranscriptionEngineError):
    """Base for all correction errors."""
    pass


class UnsupportedCorrectionProviderError(CorrectionError, NonRetryableError):
    def __init__(self, provider):
        super().__init__(f"Unsupported LLM provider: {provider}")


class CorrectionAPIError(CorrectionError, RetryableError):
    def __init__(self, message):
        super().__init__(f"Correction API Error: {message}")


class CorrectionOutputTruncatedWarning(CorrectionError):
    def __init__(self, message):
        super().__init__(message)


class RawTranscriptMissingError(CorrectionError, NonRetryableError):
    def __init__(self, message="Raw transcript missing for correction."):
        super().__init__(message)
