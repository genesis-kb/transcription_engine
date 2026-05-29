import json
import re
from typing import Dict, Tuple

class ProtectedWordMasker:
    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self._load_registry()

    def _load_registry(self):
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load registry from {self.registry_path}: {e}")

        hard_words = data.get("HARD_PROTECTED", [])
        soft_words = data.get("SOFT_PROTECTED", [])

        # Create a list of tuples: (word, type)
        all_words = [(w, "hard") for w in hard_words] + [(w, "soft") for w in soft_words]

        # Sort by length descending to match longest words first
        all_words.sort(key=lambda x: len(x[0]), reverse=True)

        self.word_mapping = {}
        self.regex_patterns = []

        for idx, (word, wtype) in enumerate(all_words, start=1):
            token = f"[{idx:04d}]"
            self.word_mapping[token] = {"word": word, "type": wtype}
            
            # Escape the word for regex and use word boundaries
            escaped_word = re.escape(word)
            pattern = re.compile(rf"\b{escaped_word}\b", re.IGNORECASE)
            self.regex_patterns.append((pattern, token))

    def mask(self, text: str) -> Tuple[str, Dict]:
        """
        Masks protected words in the text with tokens.
        Returns the masked text and the token map.
        """
        masked_text = text
        for pattern, token in self.regex_patterns:
            masked_text = pattern.sub(token, masked_text)

        return masked_text, self.word_mapping
