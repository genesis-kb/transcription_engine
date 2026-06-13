import io
from pathlib import Path
from typing import Any
from pydub import AudioSegment

def _seg(audio: bytes, fmt: str) -> AudioSegment:
    return AudioSegment.from_file(io.BytesIO(audio), format="mp3" if fmt == "mp3" else "wav")

def build_chapter(chunks: list[bytes], cfg: dict[str, Any]) -> AudioSegment:
    gap = AudioSegment.silent(duration=cfg["audio"]["silence_ms_between_chunks"])
    fmt = cfg["tts"]["format"]
    out = AudioSegment.empty()
    for i, c in enumerate(chunks):
        if i: out += gap
        out += _seg(c, fmt)
    return out

def normalize_loudness(seg: AudioSegment, target_dbfs: float) -> AudioSegment:
    if seg.dBFS == float("-inf"): return seg
    return seg.apply_gain(target_dbfs - seg.dBFS)

def export_segment(seg: AudioSegment, path: Path, fmt: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    seg.export(path, format="mp3" if fmt == "mp3" else "wav")
    return path

def export_book(chapters: list[AudioSegment], cfg: dict[str, Any], out_path: Path) -> Path:
    gap = AudioSegment.silent(duration=cfg["audio"]["silence_ms_between_chapters"])
    book = AudioSegment.empty()
    for i, ch in enumerate(chapters):
        if i: book += gap
        book += ch
    book = normalize_loudness(book, cfg["audio"]["target_dbfs"])
    return export_segment(book, out_path, cfg["tts"]["format"])
