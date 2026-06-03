import time
import requests
from typing import Optional
from app.logging import get_logger
from .base_translator import BaseTranslator, TranslatorExhausted, TranslatorError

logger = get_logger()

class SarvamTranslator(BaseTranslator):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.sarvam.ai/translate"
        
    @property
    def name(self) -> str:
        return "Sarvam AI"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key != "your_sarvam_api_key_here")

    def translate(self, text: str, target_lang: str = "hi-IN", source_lang: str = "en-IN", max_retries: int = 4) -> str:
        if not self.is_available():
            logger.warning("SARVAM_API_KEY is not configured or is a placeholder.")
            raise TranslatorError("Sarvam AI not configured")

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Instruction embedded directly in the prompt or text as per requirements.
        # Sarvam Translate v2 doesn't have a system prompt field in the generic API, 
        # but we can try adding instructions if supported, or just trust it handles brackets.
        # The documentation for Sarvam translate:
        # payload = { "input": text, "source_language_code": "en-IN", "target_language_code": "hi-IN", "speaker_gender": "Male", "mode": "formal", "model": "sarvam-translate" }
        
        payload = {
            "input": text,
            "source_language_code": source_lang,
            "target_language_code": target_lang,
            "speaker_gender": "Male",
            "mode": "formal",
            "model": "sarvam-translate:v1"
        }

        for attempt in range(max_retries):
            try:
                response = requests.post(self.base_url, json=payload, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    # Assuming response format: {"translated_text": "..."}
                    # Documentation may vary, typically it's translated_text
                    return data.get("translated_text", text)
                elif response.status_code in [429, 503]:
                    wait = 2 ** attempt * 5
                    logger.warning(f"Sarvam AI rate limited (status {response.status_code}), attempt {attempt+1}, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"Sarvam API error {response.status_code}: {response.text}")
                    raise TranslatorError(f"Sarvam API error {response.status_code}: {response.text}")
            except Exception as e:
                logger.error(f"Sarvam API exception: {e}")
                if attempt == max_retries - 1:
                    raise TranslatorExhausted(f"Sarvam max retries exhausted: {e}")
                time.sleep(2 ** attempt * 5)
                
        raise TranslatorExhausted("Sarvam max retries exhausted due to rate limits")
