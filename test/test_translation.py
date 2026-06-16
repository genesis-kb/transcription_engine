import os
import re
import pytest
import requests
import requests.exceptions
from unittest.mock import MagicMock, patch

from app.services.translation.chunker import FixedBlockChunker
from app.services.translation.restorer import TokenRestorer
from app.services.translation.gemma_client import GemmaTranslator
from app.services.translation.sarvam_client import SarvamTranslator
from app.services.translation.fallback_translator import FallbackTranslator
from app.services.translation.masker import ProtectedWordMasker
from app.services.translation.base_translator import TranslatorError, TranslatorExhausted
from routes.translation import validate_and_get_output_path, BASE_OUTPUT_DIR

# --- 1. Chunker Tests ---
def test_chunker_validation():
    with pytest.raises(ValueError, match="max_size must be an integer"):
        FixedBlockChunker(max_size="3000")
    with pytest.raises(ValueError, match="max_size must be an integer"):
        FixedBlockChunker(max_size=True) # bool is subclass of int in python
    with pytest.raises(ValueError, match="max_size must be greater than 0"):
        FixedBlockChunker(max_size=0)
    with pytest.raises(ValueError, match="max_size must be greater than 0"):
        FixedBlockChunker(max_size=-10)

def test_chunker_splitting_and_reversibility():
    text = "This is sentence one. And sentence two!\n\nHere is paragraph two with a verylongwordthatwillnotfit."
    chunker = FixedBlockChunker(max_size=25)
    
    # Split
    chunks = chunker.split(text)
    
    # Verify all chunks are within size limits
    for chunk in chunks:
        assert len(chunk) <= 25
        
    # Verify reversibility
    reconstructed = chunker.stitch(chunks)
    assert reconstructed == text

def test_chunker_edge_cases():
    chunker = FixedBlockChunker(max_size=5)
    text = "a" * 15
    chunks = chunker.split(text)
    assert chunks == ["aaaaa", "aaaaa", "aaaaa"]
    assert chunker.stitch(chunks) == text

# --- 2. Restorer Tests ---
def test_restorer_state_isolation():
    mock_translator = MagicMock()
    mock_translator.translate.side_effect = lambda word, target_lang: f"trans_{word}"
    
    restorer = TokenRestorer(mock_translator)
    
    token_map = {
        "[0001]": {"word": "Bitcoin", "type": "soft"}
    }
    
    # Call 1
    res1 = restorer.restore("[0001]", token_map)
    assert "trans_Bitcoin (Bitcoin)" in res1
    
    # Call 2 with same restorer instance: should treat as first occurrence again
    res2 = restorer.restore("[0001]", token_map)
    assert "trans_Bitcoin (Bitcoin)" in res2

# --- 3. Gemma Translator Tests ---
@patch("app.services.translation.gemma_client.ollama")
def test_gemma_translator_languages(mock_ollama):
    mock_ollama.generate.return_value = {"response": "नमस्ते"}
    translator = GemmaTranslator(model_name="gemma3:4b")
    
    # Test translate Hindi
    res = translator.translate("Hello", target_lang="hi-IN")
    assert res == "नमस्ते"
    
    # Check that target lang was used dynamically in prompt
    called_prompt = mock_ollama.generate.call_args[1]["prompt"]
    assert "Hindi" in called_prompt
    assert "Devanagari" in called_prompt

@patch("app.services.translation.gemma_client.ollama")
def test_gemma_translator_exceptions(mock_ollama):
    translator = GemmaTranslator()
    
    # KeyboardInterrupt and SystemExit must be re-raised
    mock_ollama.generate.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        translator.translate("Hello")
        
    # Other exceptions should be caught and log traceback, return fallback
    mock_ollama.generate.side_effect = ValueError("Ollama crashed")
    res = translator.translate("Hello")
    assert res == "Hello"

@patch("app.services.translation.gemma_client.ollama")
def test_gemma_is_available(mock_ollama):
    translator = GemmaTranslator(model_name="gemma3:4b")
    
    # Mocking list returning similar model name (substring match) vs exact match
    mock_ollama.list.return_value = {
        "models": [{"name": "gemma3:4b-it", "model": "gemma3:4b-it"}]
    }
    assert not translator.is_available() # Should be False since it's not exact
    
    mock_ollama.list.return_value = {
        "models": [{"name": "gemma3:4b", "model": "gemma3:4b"}]
    }
    assert translator.is_available() # True now

# --- 4. Sarvam Translator Tests ---
@patch("app.services.translation.sarvam_client.requests.post")
def test_sarvam_translator_timeout_and_exceptions(mock_post):
    translator = SarvamTranslator(api_key="valid_key", timeout=12.5)
    assert translator.timeout == 12.5
    
    # Mock success to check timeout parameter
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"translated_text": "नमस्ते"}
    mock_post.return_value = mock_response
    
    res = translator.translate("Hello")
    assert res == "नमस्ते"
    assert mock_post.call_args[1]["timeout"] == 12.5
    
    # Non-retriable TranslatorError must not be caught/retried in retry loop
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    with pytest.raises(TranslatorError):
        translator.translate("Hello", max_retries=2)
        
    # Network exception should retry and then raise TranslatorExhausted from the original error
    mock_post.side_effect = requests.exceptions.ConnectionError("Connection timed out")
    with pytest.raises(TranslatorExhausted) as exc_info:
        translator.translate("Hello", max_retries=2)
    assert exc_info.value.__cause__ is not None

# --- 5. Fallback Translator Recovery Tests ---
def test_fallback_translator_recovery():
    mock_primary = MagicMock()
    mock_fallback = MagicMock()
    
    mock_primary.is_available.return_value = False
    mock_fallback.is_available.return_value = True
    
    mock_fallback.translate.side_effect = lambda text, lang: f"fallback_{text}"
    mock_primary.translate.side_effect = lambda text, lang: f"primary_{text}"
    
    translator = FallbackTranslator(primary=mock_primary, fallback=mock_fallback)
    
    # Trigger fallback
    res = translator.translate("text1")
    assert res == "fallback_text1"
    assert translator._using_fallback is True
    
    # First 4 calls: stays on fallback
    for i in range(4):
        assert translator.translate(f"t{i}") == f"fallback_t{i}"
        
    # 5th fallback call: checks primary recovery
    # Let's say primary is now available
    mock_primary.is_available.return_value = True
    res = translator.translate("text5")
    # Should attempt primary now
    assert res == "primary_text5"
    assert translator._using_fallback is False

# --- 6. Masker Lookaround Tests ---
def test_masker_negative_lookaround_boundaries(tmp_path):
    reg_file = tmp_path / "registry.json"
    import json
    with open(reg_file, "w") as f:
        json.dump({
            "HARD_PROTECTED": ["C++", "bitcoin-core", "U.S."],
            "SOFT_PROTECTED": []
        }, f)
        
    masker = ProtectedWordMasker(str(reg_file))
    
    text = "We use C++ in bitcoin-core for U.S. markets."
    masked, mapping = masker.mask(text)
    
    # Verify that term containing punctuation was correctly masked
    # C++ ends with non-word character '+', which failed with \b
    assert "C++" not in masked
    assert "bitcoin-core" not in masked
    assert "U.S." not in masked

# --- 7. Validation / Path Traversal Tests ---
def test_path_traversal_validation():
    # Valid output path
    path = validate_and_get_output_path("output_dir", "source.txt", "hi-IN")
    assert path.startswith(BASE_OUTPUT_DIR)
    
    # Directory traversal input
    with pytest.raises(ValueError, match="Directory traversal attempt detected"):
        validate_and_get_output_path("../escape", "source.txt", "hi-IN")
        
    # Traversal via output_filename
    with pytest.raises(ValueError, match="Directory traversal attempt detected"):
        validate_and_get_output_path("output_dir", "source.txt", "hi-IN", output_filename="../../escape.md")
        
    # Absolute path in output_filename: should be relative to BASE_OUTPUT_DIR
    path2 = validate_and_get_output_path("output_dir", "source.txt", "hi-IN", output_filename="/abs/path.md")
    assert path2.startswith(BASE_OUTPUT_DIR)
    assert path2.endswith("abs/path.md")
