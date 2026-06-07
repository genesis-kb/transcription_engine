from app.exceptions.base import NonRetryableError, RetryableError, TranscriptionEngineError


class PipelineConfigError(NonRetryableError):
    """Base for configuration errors during pipeline setup."""
    pass


class MissingEnvironmentVariableError(PipelineConfigError):
    def __init__(self, var_name, custom_message=None):
        error_message = (
            custom_message
            or f"{var_name} is not set in the environment or .env file. Please set it and restart the server."
        )
        super().__init__(error_message)


class InvalidConfigValueError(PipelineConfigError):
    def __init__(self, message):
        super().__init__(message)


class UsernameRequiredError(PipelineConfigError):
    def __init__(self, message="You need to provide a username for transcription attribution"):
        super().__init__(message)


class ReviewFlagConfigError(PipelineConfigError):
    def __init__(self, message="The `--needs-review` flag is only applicable when creating a markdown"):
        super().__init__(message)


class PipelineStageError(TranscriptionEngineError):
    def __init__(self, stage_name, error_details):
        super().__init__(f"Pipeline stage '{stage_name}' failed: {error_details}")


class ExportError(TranscriptionEngineError):
    """Base for all export errors."""
    pass


class MissingTranscriptContentError(NonRetryableError):
    def __init__(self, message="No transcript content found"):
        super().__init__(message)


class FileWriteError(NonRetryableError):
    def __init__(self, file_path, error_details):
        super().__init__(f"Error writing to file {file_path}: {error_details}")


class GitHubAPIError(RetryableError):
    def __init__(self, message):
        super().__init__(f"GitHub API Error: {message}")


class GitHubAuthError(NonRetryableError):
    def __init__(self, message):
        super().__init__(f"GitHub Auth Error: {message}")


class GitHubRateLimitError(GitHubAPIError):
    def __init__(self, message):
        super().__init__(message)


class MetadataExtractionError(TranscriptionEngineError):
    def __init__(self, message):
        super().__init__(f"Metadata extraction failed: {message}")


class MetadataParseError(MetadataExtractionError):
    def __init__(self, message):
        super().__init__(f"Failed to parse metadata: {message}")
