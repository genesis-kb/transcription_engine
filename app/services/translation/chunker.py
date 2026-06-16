import re
import threading
from typing import List

class FixedBlockChunker:
    def __init__(self, max_size: int = 3000):
        if not isinstance(max_size, int) or isinstance(max_size, bool):
            raise ValueError("max_size must be an integer")
        if max_size <= 0:
            raise ValueError("max_size must be greater than 0")
        self.max_size = max_size
        self._local = threading.local()

    def split(self, text: str) -> List[str]:
        """
        Splits text into chunks of roughly max_size characters,
        preferentially breaking at paragraph or sentence boundaries.
        """
        if not isinstance(text, str):
            text = str(text)

        if len(text) <= self.max_size:
            self._local.separators = []
            return [text]

        paragraphs_and_seps = re.split(r'(\n\n)', text)
        
        units = []
        seps = []
        
        for i in range(0, len(paragraphs_and_seps), 2):
            para = paragraphs_and_seps[i]
            para_sep = paragraphs_and_seps[i+1] if i+1 < len(paragraphs_and_seps) else None
            
            if len(para) <= self.max_size:
                units.append(para)
                if para_sep is not None:
                    seps.append(para_sep)
            else:
                sentences_and_seps = re.split(r'((?<=[.!?])\s+)', para)
                for j in range(0, len(sentences_and_seps), 2):
                    sent = sentences_and_seps[j]
                    sent_sep = sentences_and_seps[j+1] if j+1 < len(sentences_and_seps) else None
                    
                    if len(sent) <= self.max_size:
                        units.append(sent)
                        if sent_sep is not None:
                            seps.append(sent_sep)
                        elif para_sep is not None:
                            seps.append(para_sep)
                    else:
                        word_parts = re.split(r'( +)', sent)
                        for k in range(0, len(word_parts), 2):
                            w = word_parts[k]
                            w_sep = word_parts[k+1] if k+1 < len(word_parts) else None
                            
                            if len(w) <= self.max_size:
                                units.append(w)
                                if w_sep is not None:
                                    seps.append(w_sep)
                                elif sent_sep is not None:
                                    seps.append(sent_sep)
                                elif para_sep is not None:
                                    seps.append(para_sep)
                            else:
                                for idx in range(0, len(w), self.max_size):
                                    slice_part = w[idx:idx+self.max_size]
                                    units.append(slice_part)
                                    if idx + self.max_size < len(w):
                                        seps.append("")
                                    else:
                                        if w_sep is not None:
                                            seps.append(w_sep)
                                        elif sent_sep is not None:
                                            seps.append(sent_sep)
                                        elif para_sep is not None:
                                            seps.append(para_sep)

        if not units:
            self._local.separators = []
            return []

        chunks = []
        self._local.separators = []
        
        current_chunk = units[0]
        for i in range(1, len(units)):
            unit = units[i]
            sep = seps[i-1]
            if len(current_chunk) + len(sep) + len(unit) <= self.max_size:
                current_chunk = current_chunk + sep + unit
            else:
                chunks.append(current_chunk)
                self._local.separators.append(sep)
                current_chunk = unit
        chunks.append(current_chunk)
        return chunks

    def stitch(self, chunks: List[str]) -> str:
        """
        Concatenates translated chunks back together.
        """
        if not chunks:
            return ""
        result = chunks[0]
        separators = getattr(self._local, "separators", None)
        if separators is not None and len(separators) == len(chunks) - 1:
            for i in range(1, len(chunks)):
                result += separators[i-1] + chunks[i]
        else:
            result = "\n\n".join(chunks)
        return result
