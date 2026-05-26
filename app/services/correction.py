import re
import time

import openai
from google import genai
from google.genai.types import GenerateContentConfig

from app.config import settings
from app.logging import get_logger
from app.services.global_tag_manager import GlobalTagManager
from app.transcript import Transcript


logger = get_logger()

MAX_CHUNK_SIZE = 5000
MIN_LENGTH_RATIO = 0.7
MAX_LENGTH_RATIO = 1.3
CONTEXT_WINDOW_CHARS = 500


class CorrectionService:
    def __init__(self, provider="openai", model="gpt-4o"):
        self.provider = provider
        self.model = model
        self.tag_manager = GlobalTagManager()
        if self.provider == "openai":
            self.client = openai
            self.client.api_key = settings.OPENAI_API_KEY
        elif self.provider == "google":
            self._client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            if self.model == "gpt-4o":  # Default overwrite for google
                self.model = "gemini-3-flash-preview"
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def _split_into_chunks(
        self, text: str, max_size: int = MAX_CHUNK_SIZE
    ) -> list[str]:
        """Split text into chunks at paragraph boundaries."""
        if len(text) <= max_size:
            return [text]

        chunks = []
        paragraphs = text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 > max_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para
            else:
                current_chunk = (
                    current_chunk + "\n\n" + para if current_chunk else para
                )

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    @staticmethod
    def _snap_to_word_boundary(text: str, max_chars: int, snap_end: bool = True) -> str:
        """Extract a context window from text, snapping to the nearest word boundary.

        Args:
            text: The source text to extract context from.
            max_chars: Maximum number of characters for the context window.
            snap_end: If True, take from the END of text (pre-context).
                      If False, take from the START of text (lookahead).

        Returns:
            A cleanly sliced context string that never cuts a word in half.
        """
        if len(text) <= max_chars:
            return text

        if snap_end:
            # Take the last ~max_chars, then trim to the nearest word start
            raw_slice = text[-max_chars:]
            # Find the first whitespace to skip any partial word at the start
            match = re.search(r"\s", raw_slice)
            if match:
                return raw_slice[match.end():]
            return raw_slice
        else:
            # Take the first ~max_chars, then trim to the nearest word end
            raw_slice = text[:max_chars]
            # Find the last whitespace to skip any partial word at the end
            match = re.search(r"\s\S*$", raw_slice)
            if match:
                return raw_slice[:match.start()]
            return raw_slice

    def process(self, transcript: Transcript, **kwargs):
        logger.info(
            f"Correcting transcript with {self.provider} (model: {self.model})..."
        )
        keywords = kwargs.get("keywords", [])

        metadata = transcript.source.to_json()
        global_context = self.tag_manager.get_correction_context()

        raw_text = transcript.outputs["raw"]
        text_length = len(raw_text)
        logger.info(f"Transcript length: {text_length} characters")

        chunks = self._split_into_chunks(raw_text)
        num_chunks = len(chunks)

        if num_chunks > 1:
            logger.info(
                f"Splitting transcript into {num_chunks} chunks for processing..."
            )

        corrected_chunks = []
        for i, chunk in enumerate(chunks, 1):
            if num_chunks > 1:
                logger.info(
                    f"Processing chunk {i}/{num_chunks} ({len(chunk)} chars)..."
                )

            pre_context = ""
            lookahead = ""

            if i > 1:
                pre_context = self._snap_to_word_boundary(
                    chunks[i-2], CONTEXT_WINDOW_CHARS, snap_end=True
                )

            if i < num_chunks:
                lookahead = self._snap_to_word_boundary(
                    chunks[i], CONTEXT_WINDOW_CHARS, snap_end=False
                )

            if pre_context or lookahead:
                logger.debug(
                    f"[CoS2W] chunk {i}/{num_chunks}: "
                    f"pre_context={len(pre_context)} chars, "
                    f"lookahead={len(lookahead)} chars"
                )

            prompt = self._build_enhanced_prompt(
                chunk, keywords, metadata, global_context, pre_context, lookahead
            )

            try:
                if self.provider == "openai":
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        timeout=300,  # 5 minute timeout
                    )
                    corrected_text = response.choices[0].message.content
                elif self.provider == "google":
                    corrected_text = self._call_with_retry(prompt, max_tokens=16384)

                # Validate output length — reject truncated or bloated responses
                length_ratio = len(corrected_text) / len(chunk) if len(chunk) > 0 else 1.0
                if length_ratio < MIN_LENGTH_RATIO:
                    logger.warning(
                        f"[CORRECTION TRUNCATED] chunk {i}/{num_chunks}: "
                        f"output {len(corrected_text)} chars vs input {len(chunk)} chars "
                        f"({length_ratio:.0%}). Using original."
                    )
                    corrected_chunks.append(chunk)
                elif length_ratio > MAX_LENGTH_RATIO:
                    logger.warning(
                        f"[CORRECTION BLOATED] chunk {i}/{num_chunks}: "
                        f"output {len(corrected_text)} chars vs input {len(chunk)} chars "
                        f"({length_ratio:.0%}). Context bleed suspected. Using original."
                    )
                    corrected_chunks.append(chunk)
                else:
                    corrected_chunks.append(corrected_text)
                    logger.info(
                        f"Chunk {i}/{num_chunks} correction complete "
                        f"({len(chunk)} -> {len(corrected_text)} chars)."
                    )

            except Exception as e:
                logger.error(
                    f"[CORRECTION FAILED] chunk {i}/{num_chunks}: {type(e).__name__}: {e}"
                )
                corrected_chunks.append(chunk)
                logger.warning(
                    f"[CORRECTION FALLBACK] Using original text for chunk {i}/{num_chunks}"
                )

            # Rate limit between chunks to avoid 429/503
            if self.provider == "google" and i < num_chunks:
                time.sleep(2)

        # Combine all corrected chunks
        transcript.outputs["corrected_text"] = "\n\n".join(corrected_chunks)
        logger.info(
            f"Correction complete. Total corrected length: {len(transcript.outputs['corrected_text'])} chars"
        )

    def _call_with_retry(self, prompt, max_tokens=8192, max_retries=4):
        """Call Gemini with exponential backoff on 503/429 errors."""
        config = GenerateContentConfig(max_output_tokens=max_tokens)
        for attempt in range(max_retries):
            try:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                return response.text
            except Exception as e:
                if ("503" in str(e) or "429" in str(e)) and attempt < max_retries - 1:
                    wait = 2 ** attempt * 5  # 5, 10, 20, 40 seconds
                    logger.warning(f"Gemini rate limited (attempt {attempt+1}), waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def _build_enhanced_prompt(self, text, keywords, metadata, global_context, pre_context="", lookahead=""):
        prompt = (
            "You are a transcript correction specialist with expertise in Bitcoin and blockchain terminology.\n\n"
            "The following transcript was generated by automatic speech recognition (ASR). Your task is to "
            "correct ONLY the obvious mistakes while keeping the transcript as close to the original as possible.\n\n"
            "DO NOT:\n"
            "- Rephrase or rewrite sentences\n"
            "- Change the speaker's style or tone\n"
            "- Add or remove content\n"
            "- Make major structural changes\n\n"
            "DO:\n"
            "- Fix spelling errors and typos\n"
            "- Correct misheard words using context\n"
            "- Fix technical terminology and proper names\n"
            "- Maintain the exact same flow and structure\n\n"
            "--- Current Video Metadata ---\n"
        )

        if metadata.get("title"):
            prompt += f"Video Title: {metadata['title']}\n"
        if metadata.get("speakers"):
            prompt += f"Speakers: {', '.join(metadata['speakers'])}\n"
        if metadata.get("tags"):
            prompt += f"Video Tags: {', '.join(metadata['tags'])}\n"
        if metadata.get("categories"):
            prompt += f"Categories: {', '.join(metadata['categories'])}\n"
        if metadata.get("youtube", {}).get("description"):
            description = (
                metadata["youtube"]["description"][:200] + "..."
                if len(metadata["youtube"]["description"]) > 200
                else metadata["youtube"]["description"]
            )
            prompt += f"Description: {description}\n"

        video_count = global_context.get("video_count", 0)
        prompt += f"\n--- Global Bitcoin Knowledge Base (From {video_count} Transcripts) ---\n"

        if global_context.get("frequent_tags"):
            frequent_tags = global_context["frequent_tags"][:15]
            prompt += f"Most Common Topics: {', '.join(frequent_tags)}\n"

        if global_context.get("technical_terms"):
            tech_terms = global_context["technical_terms"][:20]
            prompt += f"Technical Terms to Recognize: {', '.join(tech_terms)}\n"

        if global_context.get("project_names"):
            projects = global_context["project_names"][:15]
            prompt += f"Bitcoin Projects/Tools: {', '.join(projects)}\n"

        if global_context.get("common_speakers"):
            speakers = global_context["common_speakers"][:10]
            prompt += f"Frequent Speakers: {', '.join(speakers)}\n"

        if global_context.get("common_categories"):
            categories = global_context["common_categories"][:8]
            prompt += f"Common Content Categories: {', '.join(categories)}\n"

        if global_context.get("expertise_areas"):
            areas = global_context["expertise_areas"][:8]
            prompt += f"Domain Expertise Areas: {', '.join(areas)}\n"

        if global_context.get("domain_context"):
            prompt += (
                f"Primary Domain Focus: {global_context['domain_context']}\n"
            )

        prompt += "\n--- Focus Areas for Correction ---\n"
        prompt += (
            "Using the metadata and global knowledge, focus on correcting:\n"
        )
        prompt += (
            "1. Technical terms (ensure proper spelling and capitalization)\n"
        )
        prompt += (
            "2. Speaker names and project names (match known variations)\n"
        )
        prompt += "3. Common ASR mishears (but, bit, big -> Bitcoin when context suggests it)\n"
        prompt += (
            "4. Homophones and similar-sounding words in Bitcoin context\n"
        )
        prompt += "5. Obvious typos and spelling mistakes\n\n"
        prompt += "IMPORTANT: Make minimal changes - only fix clear errors, don't improve the text.\n"

        if global_context.get("tag_variations"):
            variations = global_context["tag_variations"]
            if variations:
                prompt += "\n--- Common Term Variations ---\n"
                for base_term, variants in list(variations.items())[:5]:
                    prompt += f"{base_term}: {', '.join(variants)}\n"

        if keywords:
            prompt += (
                "\n--- Additional Priority Keywords ---\n"
                "Pay special attention to these terms and ensure correct spelling/formatting:\n- "
            )
            prompt += "\n- ".join(keywords)

        # --- CoS2W: Temporal ordering (pre_context → focus chunk → lookahead) ---
        if pre_context:
            prompt += "\n\n--- Pre-Context (READ ONLY — DO NOT include in output) ---\n"
            prompt += "This is the end of the PREVIOUS transcript segment, provided only to resolve "
            prompt += "pronouns, references, and incomplete thoughts at the start of the current segment.\n\n"
            prompt += f"{pre_context}\n"

        prompt += f"\n\n--- Transcript Start (CORRECT THIS SECTION ONLY) ---\n\n{text.strip()}\n\n--- Transcript End ---\n\n"

        if lookahead:
            prompt += "--- Lookahead (READ ONLY — DO NOT include in output) ---\n"
            prompt += "This is the start of the NEXT transcript segment, provided only to prevent "
            prompt += "premature sentence closures if the speaker's thought continues beyond this chunk.\n\n"
            prompt += f"{lookahead}\n\n"

        if pre_context or lookahead:
            prompt += "Return ONLY the corrected text from between '--- Transcript Start ---' and '--- Transcript End ---'. "
            prompt += "Do NOT include any text from the Pre-Context or Lookahead sections. "
        prompt += "Return the COMPLETE corrected transcript — same length, same structure. "
        prompt += "Do NOT summarize, shorten, or skip any lines. "
        prompt += "Keep all speaker labels, timestamps, and filler words. "
        prompt += "Make minimal changes — fix only obvious errors while "
        prompt += "preserving the original wording, sentence structure, and speaker's natural expression."

        return prompt

    def _build_prompt(self, text, keywords, metadata):
        """Legacy method for backward compatibility"""
        return self._build_enhanced_prompt(text, keywords, metadata, {})
