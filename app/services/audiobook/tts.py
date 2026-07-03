from __future__ import annotations

import requests
from abc import ABC, abstractmethod
from typing import Any, Optional
import re

class TTSProvider(ABC):
    name: str = "base"
    supported_formats: set[str] = {"mp3", "wav"}

    def __init__(self, api_key: str, voice: str, fmt: str = "mp3",
                 speed: float = 1.0, model: str | None = None,
                 lexicon: dict[str, str] | None = None):
        if fmt not in self.supported_formats:
            raise ValueError(
                f"Unsupported format '{fmt}' for {self.name} provider. "
                f"Must be one of: {sorted(self.supported_formats)}"
            )
        self.api_key = api_key
        self.voice = voice
        self.fmt = fmt
        self.speed = speed
        self.model = model
        self.lexicon = lexicon or {}

    def apply_lexicon_fallback(self, text: str) -> str:
        """Applies regex text substitution as a fallback for providers without native lexicon support."""
        if not self.lexicon:
            return text
        for key in sorted(self.lexicon, key=len, reverse=True):
            pattern = re.compile(rf"\b{re.escape(key)}\b", re.IGNORECASE)
            text = pattern.sub(self.lexicon[key], text)
        return text

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        raise NotImplementedError

class DeepgramTTS(TTSProvider):
    name = "deepgram"
    supported_formats = {"mp3", "wav", "linear16"}

    def synthesize(self, text: str) -> bytes:
        text = self.apply_lexicon_fallback(text)
        _MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "linear16": "audio/wav"}
        params = {"model": self.voice, "encoding": "mp3" if self.fmt == "mp3" else "linear16"}
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
            "Accept": _MIME.get(self.fmt, "audio/mpeg"),
        }
        resp = requests.post("https://api.deepgram.com/v1/speak", params=params, headers=headers,
                             json={"text": text}, timeout=120)
        resp.raise_for_status()
        return resp.content

class SmallestTTS(TTSProvider):
    name = "smallest"
    supported_formats = {"mp3", "wav", "pcm"}

    def synthesize(self, text: str) -> bytes:
        text = self.apply_lexicon_fallback(text)
        _ACCEPT = {"mp3": "audio/mpeg", "wav": "audio/wav", "pcm": "audio/pcm"}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": _ACCEPT.get(self.fmt, "audio/mpeg"),
        }
        payload = {
            "text": text,
            "voice_id": self.voice,
            "speed": self.speed,
            "sample_rate": 24000,
            "output_format": self.fmt,
        }
        if self.model:
            payload["model"] = self.model
        resp = requests.post("https://api.smallest.ai/waves/v1/tts", headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.content

def make_provider(cfg: dict[str, Any], lexicon: dict[str, str] | None = None) -> TTSProvider:
    _REGISTRY = {"deepgram": DeepgramTTS, "smallest": SmallestTTS}
    name = cfg["tts"]["provider"]
    if name not in _REGISTRY:
        raise ValueError(f"Unknown TTS provider '{name}'. Options: {list(_REGISTRY)}")
    
    api_key = cfg["keys"].get(name, "")
    if not api_key:
        env_var = f"{name.upper()}_API_KEY"
        raise ValueError(f"Missing API key for TTS provider '{name}'. Please set the {env_var} environment variable.")
        
    return _REGISTRY[name](
        api_key=api_key,
        voice=cfg["tts"]["voices"][name],
        fmt=cfg["tts"]["format"],
        speed=cfg["tts"].get("speed", 1.0),
        model=cfg["tts"].get("models", {}).get(name),
        lexicon=lexicon,
    )
