from app.logging import get_logger
from .base_translator import BaseTranslator, TranslatorExhausted, TranslatorError

logger = get_logger()

class FallbackTranslator(BaseTranslator):
    def __init__(self, primary: BaseTranslator, fallback: BaseTranslator):
        self.primary = primary
        self.fallback = fallback
        self._using_fallback = False

    @property
    def name(self) -> str:
        if self._using_fallback:
            return self.fallback.name
        return self.primary.name

    def translate(self, text: str, target_lang: str = "hi-IN") -> str:
        if self._using_fallback:
            return self.fallback.translate(text, target_lang)

        try:
            # Check if primary is even available. If not, fail fast to fallback.
            if not self.primary.is_available():
                logger.warning(f"{self.primary.name} is not available. Switching to fallback.")
                raise TranslatorError(f"{self.primary.name} unavailable")
                
            return self.primary.translate(text, target_lang)
        except (TranslatorExhausted, TranslatorError) as e:
            logger.warning(f"{self.primary.name} failed: {e}. Switching to fallback ({self.fallback.name}).")
            self._using_fallback = True
            logger.info(f"Retrying current chunk with {self.fallback.name}...")
            return self.fallback.translate(text, target_lang)

    def is_available(self) -> bool:
        return self.primary.is_available() or self.fallback.is_available()
