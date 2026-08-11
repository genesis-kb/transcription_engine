import json
import os
import time

import ollama

from app.logging import get_logger
from app.transcript import Transcript


logger = get_logger()


class MetadataExtractorService:
    """
    Extracts structured metadata (speakers, conference, topics) from YouTube
    video metadata using a single Gemma LLM call per video via Ollama.

    Runs as a processing service in the transcription pipeline, before
    correction and summarization, so extracted metadata enriches those steps.
    """

    def __init__(self):
        self.model = os.getenv("GEMMA_MODEL", "gemma3:4b")
        self._ollama = ollama

    def process(self, transcript: Transcript, **kwargs):
        """
        Extract metadata from a transcript's YouTube metadata.
        Updates transcript.source with extracted speakers, conference, and topics.
        Skips gracefully if no YouTube metadata is available.
        """
        source = transcript.source

        # Only run for sources with YouTube metadata
        youtube_metadata = getattr(source, "youtube_metadata", None)
        if not youtube_metadata:
            logger.debug(
                f"Skipping metadata extraction for '{source.title}': no YouTube metadata"
            )
            return

        title = source.title or ""
        description = youtube_metadata.get("description", "") or ""
        channel_name = youtube_metadata.get("channel_name", "") or ""
        tags = youtube_metadata.get("tags", []) or []
        if isinstance(tags, str):
            tags = [tags]

        logger.info(
            f"Extracting metadata for '{title}' (channel: {channel_name})..."
        )

        prompt = self._build_prompt(title, description, channel_name, tags)

        try:
            logger.info(f"(metadata_extractor) Loading model '{self.model}'...")
            self._load_gemma_model()
            
            response = self._call_with_retry(prompt)
            extracted = self._parse_response(response)

            # Update speakers only if they weren't manually provided
            if not source.speakers or source.speakers == []:
                extracted_speakers = extracted.get("speakers", [])
                if extracted_speakers:
                    source.speakers = extracted_speakers
                    logger.info(f"  Extracted speakers: {source.speakers}")

            # Set conference (new field)
            conference = extracted.get("conference", "")
            if conference:
                source.conference = conference
                logger.info(f"  Extracted conference: {conference}")

            # Set topics (new field)
            topics = extracted.get("topics", [])
            if topics:
                source.topics = topics
                logger.info(f"  Extracted topics: {topics}")

            logger.info(f"Metadata extraction complete for '{title}'")

        except Exception as e:
            logger.warning(
                f"Metadata extraction failed for '{title}': {e}. "
                f"Existing metadata preserved."
            )
        finally:
            self._unload_gemma_model()

    def _load_gemma_model(self):
        """Pre-load the model into memory with infinite keep_alive."""
        try:
            self._ollama.generate(model=self.model, keep_alive=-1)
        except Exception as e:
            logger.warning(f"Failed to pre-load Ollama model {self.model}: {e}")

    def _unload_gemma_model(self):
        """Unload the model from memory."""
        try:
            logger.info(f"(metadata_extractor) Unloading model '{self.model}'...")
            self._ollama.generate(model=self.model, keep_alive=0)
        except Exception as e:
            logger.warning(f"Failed to unload Ollama model {self.model}: {e}")

    def _call_with_retry(self, prompt, max_retries=3):
        """Call Gemma via Ollama with retries."""
        for attempt in range(max_retries):
            try:
                response = self._ollama.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.get("message", {}).get("content", "").strip()
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt * 5
                    logger.warning(f"Ollama rate limited/failed (attempt {attempt+1}), waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def _build_prompt(self, title, description, channel_name, tags):
        """Build the extraction prompt for the LLM."""
        # Truncate description to avoid huge prompts
        desc_truncated = (
            description[:800] if len(description) > 800 else description
        )

        tags_str = ", ".join(tags[:20]) if tags else "None"

        prompt = (
            "You are a metadata extraction specialist for Bitcoin conference talks and presentations.\n\n"
            "Given the following YouTube video metadata, extract:\n"
            "1. **speakers** - The actual person(s) giving the talk/presentation. "
            "Extract real names only, not channel names or organizations.\n"
            "2. **conference** - The conference or event name where this was presented. "
            "The YouTube channel name is often the conference/organization itself. "
            "If this appears to be a podcast, use the podcast name.\n"
            "3. **topics** - Bitcoin-specific technical topics discussed. "
            "Use specific terms like 'Lightning Network', 'Taproot', 'Mining', 'Privacy', "
            "'Multisig', 'Layer 2', 'Wallet', etc. Do NOT include generic terms like "
            "'Bitcoin' or 'Cryptocurrency' - focus on specific subtopics.\n\n"
            f"--- Video Metadata ---\n"
            f"Title: {title}\n"
            f"Channel: {channel_name}\n"
            f"Tags: {tags_str}\n"
            f"Description:\n{desc_truncated}\n"
            f"--- End Metadata ---\n\n"
            "Respond with a JSON object ONLY, nothing else. DO NOT use markdown code blocks.\n"
            '{"speakers": ["Name1", "Name2"], "conference": "Event Name", "topics": ["Topic1", "Topic2"]}\n\n'
            "Rules:\n"
            "- If speaker names cannot be determined, return an empty speakers array\n"
            "- For conference, prefer the channel name as the event identifier\n"
            "- Return 2-5 specific topics, ordered by relevance\n"
            "- Return raw JSON only, starting with '{' and ending with '}'.\n"
        )
        return prompt

    def _parse_response(self, response_text):
        """Parse the LLM response JSON, with fallback handling."""
        try:
            # Clean up potential markdown code blocks
            text = response_text.strip()
            if text.startswith("```"):
                # Remove markdown wrapper
                lines = text.split("\n")
                # Find where json actually starts if there's text before it
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            
            # Find the first { and last } in case it wrapped text around it
            start_idx = text.find("{")
            end_idx = text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                text = text[start_idx:end_idx+1]

            result = json.loads(text)

            # Validate and normalize the response
            speakers = result.get("speakers", [])
            if not isinstance(speakers, list):
                speakers = [speakers] if speakers else []
            speakers = [
                s.strip() for s in speakers if isinstance(s, str) and s.strip()
            ]

            conference = result.get("conference", "")
            if not isinstance(conference, str):
                conference = str(conference) if conference else ""
            conference = conference.strip()

            topics = result.get("topics", [])
            if not isinstance(topics, list):
                topics = [topics] if topics else []
            topics = [
                t.strip() for t in topics if isinstance(t, str) and t.strip()
            ]

            return {
                "speakers": speakers,
                "conference": conference,
                "topics": topics,
            }

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse metadata extraction response: {e}")
            logger.debug(f"Raw response: {response_text}")
            return {"speakers": [], "conference": "", "topics": []}
