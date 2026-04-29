import time
import openai
from google import genai
from google.genai.types import GenerateContentConfig

from app.config import settings
from app.logging import get_logger

logger = get_logger()

def parse_model_string(model_string: str, default_provider: str = "openai") -> tuple[str, str]:
    """Parse a model string like 'openai:gpt-4o' or just 'gpt-4o' into provider and model."""
    if ":" in model_string:
        provider, model = model_string.split(":", 1)
        return provider.lower(), model
    return default_provider, model_string

def call_llm(model_string: str, prompt: str, max_tokens: int = 8192, default_provider: str = "openai") -> str:
    """Central point to call different LLM providers."""
    provider, model = parse_model_string(model_string, default_provider)
    if provider == "openai":
        return call_openai(model, prompt, max_tokens)
    elif provider in ["google", "gemini"]:
        return call_gemini(model, prompt, max_tokens)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

def call_openai(model: str, prompt: str, max_tokens: int = 8192) -> str:
    """Call OpenAI API."""
    try:
        openai.api_key = settings.OPENAI_API_KEY
        response = openai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            timeout=300,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise

def call_gemini(model: str, prompt: str, max_tokens: int = 8192, max_retries: int = 4) -> str:
    """Call Gemini API with exponential backoff on rate limits."""
    client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    config = GenerateContentConfig(max_output_tokens=max_tokens)
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            return response.text
        except Exception as e:
            if ("503" in str(e) or "429" in str(e)) and attempt < max_retries - 1:
                wait = 2 ** attempt * 5
                logger.warning(f"Gemini rate limited (attempt {attempt+1}), waiting {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Gemini API error: {e}")
                raise
