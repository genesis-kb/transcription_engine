from app.exceptions.base import NonRetryableError, RetryableError, TranscriptionEngineError


class SummarizationError(TranscriptionEngineError):
    """Base for all summarization errors."""
    pass


class UnsupportedSummarizationProviderError(NonRetryableError):
    def __init__(self, provider):
        super().__init__(f"Unsupported LLM provider: {provider}")


class SummarizationAPIError(SummarizationError, RetryableError):
    def __init__(self, message):
        super().__init__(f"Summarization API Error: {message}")


class EmptySummarizationInputError(SummarizationError, NonRetryableError):
    def __init__(self, message="No text provided for summarization."):
        super().__init__(message)
