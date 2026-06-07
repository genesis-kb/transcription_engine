from app.exceptions.base import NonRetryableError, RetryableError


class DuplicateSourceError(NonRetryableError):
    def __init__(self, loc, title):
        self.loc = loc
        self.title = title
        super().__init__(f"Source already exists in queue: {title} ({loc})")


class InvalidSourceError(NonRetryableError):
    def __init__(self, message):
        super().__init__(message)


class InvalidJSONSourceError(NonRetryableError):
    def __init__(self, message):
        super().__init__(message)


class SourceNotFoundInQueueError(NonRetryableError):
    def __init__(self, title):
        super().__init__(f"Source not found in queue: {title}")


class UnsupportedMediaTypeError(NonRetryableError):
    def __init__(self, message):
        super().__init__(message)


class MediaFileNotFoundError(NonRetryableError):
    def __init__(self, filepath):
        super().__init__(f"Media file not found: {filepath}")


class FFmpegInitializationError(NonRetryableError):
    def __init__(self, message="Error initializing FFMPEG"):
        super().__init__(message)


class AudioConversionError(NonRetryableError):
    def __init__(self, input_path, error_details):
        super().__init__(f"Error converting {input_path} to mp3: {error_details}")


class AudioSplitError(NonRetryableError):
    def __init__(self, message):
        super().__init__(message)


class MediaDownloadError(RetryableError):
    def __init__(self, message):
        super().__init__(message)


class MediaURLExtractionError(RetryableError):
    def __init__(self, message):
        super().__init__(message)


class ChannelScanError(RetryableError):
    def __init__(self, channel_name, error_details):
        super().__init__(f"Error scanning {channel_name}: {error_details}")


class VideoNotFoundError(NonRetryableError):
    def __init__(self, video_id):
        super().__init__(f"Video not found: {video_id}")


class VideoClassificationError(RetryableError):
    def __init__(self, message):
        super().__init__(message)


class IngestionQueueError(RetryableError):
    def __init__(self, message):
        super().__init__(message)
