import ollama
from app.logging import get_logger
from .base_translator import BaseTranslator

logger = get_logger()

class GemmaTranslator(BaseTranslator):
    def __init__(self, model_name: str = "gemma3:4b"):
        self.model_name = model_name

    @property
    def name(self) -> str:
        return f"Gemma ({self.model_name})"

    def translate(self, text: str, target_lang: str = "hi-IN") -> str:
        prompt = (
            f"You are an expert translator specializing in technical English to Hindi translations.\n"
            f"Your task is to translate the following English text into natural, fluent Hindi written entirely in the Devanagari script.\n"
            f"Adhere strictly to the following rules:\n"
            f"1. Use standard Devanagari script for all Hindi text.\n"
            f"2. Ensure the grammar and tone are appropriate for a formal, technical context.\n"
            f"3. CRITICAL: The text contains special protected tokens formatted as [0001], [0002], etc. You MUST NOT translate, modify, or remove these tokens. Leave the brackets and numbers exactly as they appear in the original text.\n"
            f"4. Do NOT provide any introductory or concluding remarks. Return ONLY the translated text.\n\n"
            f"English text to translate:\n{text}"
        )

        try:
            response = ollama.generate(model=self.model_name, prompt=prompt)
            return response.get('response', text).strip()
        except Exception as e:
            logger.error(f"Ollama execution error: {e}")
            return text

    def is_available(self) -> bool:
        try:
            resp = ollama.list()
            models = resp.get('models', [])
            return any(self.model_name in m.get('name', '') for m in models)
        except Exception:
            return False
