import os
from dataclasses import dataclass
from typing import Dict

from .masker import ProtectedWordMasker
from .chunker import FixedBlockChunker
from .sarvam_client import SarvamTranslator
from .gemma_client import GemmaTranslator
from .fallback_translator import FallbackTranslator
from .restorer import TokenRestorer
from app.logging import get_logger

logger = get_logger()

@dataclass
class TranslationResult:
    original_text: str
    masked_text: str
    token_map: Dict
    translated_text: str
    raw_translated_text: str

class TranslationPipeline:
    def __init__(self, registry_path: str, sarvam_api_key: str, target_lang: str = "hi-IN", gemma_model: str = "gemma3:4b", debug: bool = False):
        self.target_lang = target_lang
        self.masker = ProtectedWordMasker(registry_path)
        self.chunker = FixedBlockChunker(max_size=1500)
        self.debug = debug
        
        sarvam = SarvamTranslator(sarvam_api_key)
        gemma = GemmaTranslator(gemma_model)
        self.translator = FallbackTranslator(primary=sarvam, fallback=gemma)
        
        self.restorer = TokenRestorer(self.translator)

    def translate_text(self, text: str) -> TranslationResult:
        logger.info("Starting translation pipeline...")
        
        if not text.strip():
            logger.info("Input text is empty or only whitespace. Returning early.")
            return TranslationResult(
                original_text=text,
                masked_text=text,
                token_map={},
                translated_text=text,
                raw_translated_text=text
            )
        
        # Stage 1: Mask
        logger.info("Stage 1: Masking protected words...")
        masked_text, token_map = self.masker.mask(text)
        logger.info(f"Masked {len(token_map)} unique terms.")
        if self.debug:
            try:
                with open("debug_stage1_masked.txt", "w", encoding="utf-8") as f:
                    f.write(masked_text)
                logger.info("Saved intermediate masked text to debug_stage1_masked.txt")
            except Exception as e:
                logger.error(f"Failed to save debug masked text: {e}")
        
        # Stage 2: Translate via chunks
        logger.info("Stage 2: Chunking and translating...")
        chunks = self.chunker.split(masked_text)
        logger.info(f"Split into {len(chunks)} chunks.")
        
        translated_chunks = []
        for i, chunk in enumerate(chunks, 1):
            logger.info(f"Translating chunk {i}/{len(chunks)} with {self.translator.name}...")
            translated_chunk = self.translator.translate(chunk, target_lang=self.target_lang)
            translated_chunks.append(translated_chunk)
            
        raw_translated_text = self.chunker.stitch(translated_chunks)
        if self.debug:
            try:
                with open("debug_stage2_raw_translated.txt", "w", encoding="utf-8") as f:
                    f.write(raw_translated_text)
                logger.info("Saved intermediate raw translated text to debug_stage2_raw_translated.txt")
            except Exception as e:
                logger.error(f"Failed to save debug raw translated text: {e}")
        
        # Stage 3: Restore
        logger.info("Stage 3: Restoring tokens...")
        final_text = self.restorer.restore(raw_translated_text, token_map, target_lang=self.target_lang)
        
        logger.info("Translation pipeline complete.")
        
        return TranslationResult(
            original_text=text,
            masked_text=masked_text,
            token_map=token_map,
            translated_text=final_text,
            raw_translated_text=raw_translated_text
        )
