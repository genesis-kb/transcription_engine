class TranscriptionEngineError(Exception):
    """Root base class for all transcription engine errors."""
    pass

class RetryableError(TranscriptionEngineError):
    """Transient errors that are safe to retry (rate limits, timeouts, network blips)."""
    pass

class NonRetryableError(TranscriptionEngineError):
    """Permanent errors — retrying won't help."""
    pass
