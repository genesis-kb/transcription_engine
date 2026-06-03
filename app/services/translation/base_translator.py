from abc import ABC, abstractmethod

class TranslatorExhausted(Exception):
    """Raised when a translator has exhausted its retries (e.g. rate limit)."""
    pass

class TranslatorError(Exception):
    """Raised when a translator encounters a non-recoverable error."""
    pass

class BaseTranslator(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the translator."""
        ...

    @abstractmethod
    def translate(self, text: str, target_lang: str = "hi-IN") -> str:
        """Translate text. Returns translated string, or original on failure."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Quick check: is this translator configured and reachable?"""
        ...
