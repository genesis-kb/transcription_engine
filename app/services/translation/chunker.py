import re
from typing import List

class FixedBlockChunker:
    def __init__(self, max_size: int = 3000):
        self.max_size = max_size

    def split(self, text: str) -> List[str]:
        """
        Splits text into chunks of roughly max_size characters,
        preferentially breaking at paragraph or sentence boundaries.
        """
        if len(text) <= self.max_size:
            return [text]

        chunks = []
        # First try to split by paragraphs
        paragraphs = text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 > self.max_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # If a single paragraph is still larger than max_size, split by sentences
                if len(para) > self.max_size:
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    sub_chunk = ""
                    for sentence in sentences:
                        if len(sub_chunk) + len(sentence) + 1 > self.max_size:
                            if sub_chunk:
                                chunks.append(sub_chunk.strip())
                            sub_chunk = sentence
                        else:
                            sub_chunk = sub_chunk + " " + sentence if sub_chunk else sentence
                    current_chunk = sub_chunk
                else:
                    current_chunk = para
            else:
                current_chunk = current_chunk + "\n\n" + para if current_chunk else para

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def stitch(self, chunks: List[str]) -> str:
        """
        Concatenates translated chunks back together.
        """
        return "\n\n".join(chunks)
