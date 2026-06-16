import re
from typing import Dict
from .base_translator import BaseTranslator

class TokenRestorer:
    def __init__(self, translator: BaseTranslator):
        self.translator = translator

    def restore(self, text: str, token_map: Dict, target_lang: str = "hi-IN") -> str:
        """
        Restores tokens to their original/translated words based on rules:
        - hard: exact English word
        - soft: first occurrence -> translated (English), subsequent -> English
        """
        
        seen_soft_words = {}
        # We need to find tokens sequentially as they appear to handle first occurrence
        # properly. A regex that finds any [NNNN] is best.
        
        pattern = re.compile(r"\[\d{4}\]")
        
        def replace_match(match):
            token = match.group(0)
            if token not in token_map:
                return token
            
            entry = token_map[token]
            word = entry["word"]
            wtype = entry["type"]
            
            if wtype == "hard":
                return word
            elif wtype == "soft":
                if word not in seen_soft_words:
                    # Translate just the word for first occurrence
                    # In a real scenario, we might want context, but translating the single word
                    # or phrase is the requirement here.
                    translated_word = self.translator.translate(word, target_lang=target_lang)
                    seen_soft_words[word] = translated_word
                    return f"{translated_word} ({word})"
                else:
                    return word
            return word

        restored_text = pattern.sub(replace_match, text)
        return restored_text
