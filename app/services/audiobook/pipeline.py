"""Core audio generation pipeline.

Pure audio-processing engine: text in → audio files out.
Does NOT write to the database — that responsibility belongs to the
curator, which calls this pipeline and then persists the results.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from pydub import AudioSegment

from app.logging import get_logger

from .config import load_audiobook_config
from .tts import make_provider, TTSProvider
from .textproc import clean_text, normalize, chunk_split, parse_diarization
from .rewrite import rewrite
from .stitch import build_chapter, export_segment, export_book


logger = get_logger()

# Default output and cache directories (relative to project root)
DEFAULT_OUTPUT_DIR = Path("outputs/audiobooks")
DEFAULT_CACHE_DIR = Path(".cache/audiobooks")


@dataclass
class GeneratedEpisode:
    """Result of generating audio for a single episode."""

    title: str
    audio_path: Path
    duration_seconds: int
    chapters: list[dict]


def _cache_key(provider: str, voice: str, fmt: str, text: str, lex_hash: str = "") -> str:
    h = hashlib.sha256(
        f"{provider}|{voice}|{fmt}|{text}|{lex_hash}".encode("utf-8")
    )
    return h.hexdigest()[:24]


def _get_or_synthesize(
    cache_dir: Path, provider: TTSProvider, text: str
) -> bytes:
    """Synthesize a text chunk, using a local file cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    lex_str = str(sorted(provider.lexicon.items())) if getattr(provider, "lexicon", None) else ""
    lex_hash = hashlib.md5(lex_str.encode("utf-8")).hexdigest()[:8] if lex_str else ""
    key = _cache_key(provider.name, provider.voice, provider.fmt, text, lex_hash)
    path = cache_dir / f"{key}.{provider.fmt}"
    if path.exists():
        return path.read_bytes()
    audio = provider.synthesize(text)
    path.write_bytes(audio)
    return audio


class AudioPipeline:
    """Stateless audio generation pipeline.

    Converts raw text → cleaned text → (optional LLM rewrite) →
    TTS chunks → stitched audio file.
    """

    def __init__(
        self,
        cfg: Optional[dict[str, Any]] = None,
        lexicon: Optional[dict[str, str]] = None,
    ):
        if cfg and lexicon:
            self.cfg = cfg
            self.lexicon = lexicon
        else:
            self.cfg, self.lexicon = load_audiobook_config()

    def generate_episode(
        self,
        text: str,
        title: str = "Untitled",
        output_dir: Optional[Path] = None,
        skip_llm: bool = False,
        provider_override: Optional[str] = None,
        diarize: bool = False,
    ) -> GeneratedEpisode:
        """Generate a single audio episode from raw text.

        Args:
            text: Raw body text to convert.
            title: Episode title (used for the output filename).
            output_dir: Where to write the final MP3. Defaults to
                        outputs/audiobooks/<title-slug>/.
            skip_llm: If True, skip the OpenAI rewrite step.
            provider_override: Force a specific TTS provider.
            diarize: If True, parse speaker tags and assign dynamic voices.

        Returns:
            A GeneratedEpisode with the path, duration, and chapter list.
        """
        cfg = self.cfg
        if provider_override:
            cfg["tts"]["provider"] = provider_override

        provider = make_provider(cfg, self.lexicon)
        cap = cfg["tts"]["max_chars"][cfg["tts"]["provider"]]
        fmt = cfg["tts"]["format"]

        # Step 1: Clean
        logger.info(f"[pipeline] Cleaning text for '{title}' (diarize={diarize})")
        clean_txt = clean_text(text, retain_speakers=diarize)

        # Step 2: Optionally rewrite via LLM
        if skip_llm:
            manifest = {
                "title": title,
                "chapters": [{"title": title, "text": clean_txt}],
            }
        else:
            logger.info(
                f"[pipeline] LLM rewrite via {cfg['llm']['model']}"
            )
            manifest = rewrite(clean_txt, cfg)
            manifest["title"] = title  # preserve caller's title

        chapters = manifest.get("chapters", [])

        # Resolve output directory
        if output_dir is None:
            safe_title = "".join(
                c if c.isalnum() or c in " -_" else ""
                for c in title
            ).strip() or "episode"
            output_dir = DEFAULT_OUTPUT_DIR / safe_title

        cache_dir = DEFAULT_CACHE_DIR

        # Step 3+4: Normalize → chunk → TTS per chapter
        chapters_audio: list[AudioSegment] = []
        logger.info(
            f"[pipeline] TTS via {provider.name} ({provider.voice})"
        )
        # Keep a persistent voice map across chapters for consistent diarization
        speaker_voice_map = {}
        voice_idx = 0
        available_voices = [provider.voice]
        if provider.name == "deepgram":
            available_voices = ["aura-asteria-en", "aura-orion-en", "aura-arcas-en", "aura-perseus-en", "aura-helios-en", "aura-angus-en"]
        elif provider.name == "smallest":
            available_voices = ["emily", "james", "lucy", "michael", "sarah"]

        for ci, ch in enumerate(chapters, 1):
            if diarize:
                speaker_chunks = parse_diarization(ch["text"])
            else:
                speaker_chunks = [{"speaker": "default", "text": ch["text"]}]
                
            audio_chunks = []
            for spk_chunk in speaker_chunks:
                speaker = spk_chunk["speaker"]
                spoken = normalize(spk_chunk["text"])
                pieces = chunk_split(spoken, cap)
                
                original_voice = provider.voice
                if speaker != "default":
                    if speaker not in speaker_voice_map:
                        speaker_voice_map[speaker] = available_voices[voice_idx % len(available_voices)]
                        voice_idx += 1
                    provider.voice = speaker_voice_map[speaker]
                
                for p in pieces:
                    audio_chunks.append(_get_or_synthesize(cache_dir, provider, p))
                    
                provider.voice = original_voice
                
            seg = build_chapter(audio_chunks, cfg)
            export_segment(
                seg, output_dir / f"ch{ci:02d}.{fmt}", fmt
            )
            chapters_audio.append(seg)

        # Step 5: Stitch into final file
        logger.info("[pipeline] Stitching final audio")
        final_path = output_dir / f"{title}.{fmt}"
        export_book(chapters_audio, cfg, final_path)

        # Compute duration
        final_audio = AudioSegment.from_file(final_path)
        duration_seconds = int(len(final_audio) / 1000)

        return GeneratedEpisode(
            title=title,
            audio_path=final_path,
            duration_seconds=duration_seconds,
            chapters=chapters,
        )


# =====================================================================
# Backwards-compatible wrapper (preserves old import path)
# =====================================================================

class AudiobookService:
    """Legacy wrapper — delegates to AudioPipeline + PlaylistService."""

    def __init__(self):
        self._pipeline = AudioPipeline()

    def generate_from_text(
        self,
        text: str,
        skip_llm: bool = False,
        provider_override: Optional[str] = None,
        diarize: bool = False,
        **kwargs,
    ) -> Optional[dict]:
        """Generate audio from raw text and return a result dict."""
        try:
            result = self._pipeline.generate_episode(
                text=text,
                title=kwargs.get("title", "Full Text Audiobook"),
                skip_llm=skip_llm,
                provider_override=provider_override,
                diarize=diarize,
            )
            return {
                "title": result.title,
                "audio_url": str(result.audio_path.absolute()),
                "duration_seconds": result.duration_seconds,
                "chapters": result.chapters,
                "status": "completed",
            }
        except Exception as e:
            logger.error(f"Audio generation failed: {e}")
            return None
