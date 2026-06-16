from app.logging import get_logger
from .base_translator import BaseTranslator, TranslatorExhausted, TranslatorError

logger = get_logger()

class FallbackTranslator(BaseTranslator):
    def __init__(self, primary: BaseTranslator, fallback: BaseTranslator):
        self.primary = primary
        self.fallback = fallback
        self._using_fallback = False
        self._fallback_calls = 0

    @property
    def name(self) -> str:
        if self._using_fallback:
            return self.fallback.name
        return self.primary.name

    def translate(self, text: str, target_lang: str = "hi-IN") -> str:
        # Once self._using_fallback is set to True, the translator will use fallback.translate(...)
        # but will periodically attempt to recover the primary translator every 5 calls by checking primary.is_available().
        if self._using_fallback:
            self._fallback_calls += 1
            if self._fallback_calls >= 5:
                try:
                    if self.primary.is_available():
                        logger.info(f"Attempting to recover primary translator {self.primary.name} after 5 fallback calls.")
                        self._using_fallback = False
                        self._fallback_calls = 0
                except Exception:
                    pass

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
            self._fallback_calls = 0
            logger.info(f"Retrying current chunk with {self.fallback.name}...")
            return self.fallback.translate(text, target_lang)

    def is_available(self) -> bool:
        return self.primary.is_available() or self.fallback.is_available()
