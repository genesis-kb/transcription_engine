"""Tests for app.services.audiobook.tts — Groups 7-8."""

import pytest
from app.services.audiobook.tts import (
    DeepgramTTS,
    SmallestTTS,
    TTSProvider,
    make_provider,
)


# ── Group 7: make_provider ───────────────────────────────────────────

@pytest.mark.unit
class TestMakeProvider:
    def test_deepgram_provider(self, sample_cfg):
        p = make_provider(sample_cfg)
        assert isinstance(p, DeepgramTTS)

    def test_smallest_provider(self, sample_cfg):
        sample_cfg["tts"]["provider"] = "smallest"
        p = make_provider(sample_cfg)
        assert isinstance(p, SmallestTTS)

    def test_unknown_provider_raises(self, sample_cfg):
        sample_cfg["tts"]["provider"] = "unknown"
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            make_provider(sample_cfg)

    def test_missing_api_key_raises(self, sample_cfg):
        sample_cfg["keys"]["deepgram"] = ""
        with pytest.raises(ValueError, match="Missing API key"):
            make_provider(sample_cfg)

    def test_unsupported_format_raises(self, sample_cfg):
        sample_cfg["tts"]["format"] = "flac"
        with pytest.raises(ValueError, match="Unsupported format"):
            make_provider(sample_cfg)


# ── Group 8: apply_lexicon_fallback ──────────────────────────────────

@pytest.mark.unit
class TestLexiconFallback:
    def _make_provider(self, lexicon):
        return DeepgramTTS(
            api_key="test", voice="test-voice", fmt="mp3", lexicon=lexicon,
        )

    def test_known_term_replaced(self):
        p = self._make_provider({"DeFi": "dee-fye"})
        assert p.apply_lexicon_fallback("DeFi is hot") == "dee-fye is hot"

    def test_case_insensitive(self):
        p = self._make_provider({"DeFi": "dee-fye"})
        assert "dee-fye" in p.apply_lexicon_fallback("defi rocks")

    def test_longer_key_first(self):
        p = self._make_provider({"Bitcoin": "BTC", "Bitcoin Cash": "BCH"})
        result = p.apply_lexicon_fallback("I like Bitcoin Cash")
        assert "BCH" in result
        assert "BTC" not in result

    def test_empty_lexicon(self):
        p = self._make_provider({})
        assert p.apply_lexicon_fallback("anything") == "anything"
