import io
from pathlib import Path
from typing import Any
from pydub import AudioSegment

def _seg(audio: bytes, fmt: str) -> AudioSegment:
    return AudioSegment.from_file(io.BytesIO(audio), format=fmt)

def build_chapter(chunks: list[bytes], cfg: dict[str, Any]) -> AudioSegment:
    if not chunks:
        return AudioSegment.empty()
    
    fmt = cfg["tts"]["format"]
    first = _seg(chunks[0], fmt)
    
    gap = AudioSegment.silent(
        duration=cfg["audio"]["silence_ms_between_chunks"],
        frame_rate=first.frame_rate
    ).set_channels(first.channels).set_sample_width(first.sample_width)
    
    segments = [first]
    for c in chunks[1:]:
        segments.append(gap)
        seg = _seg(c, fmt)
        seg = seg.set_frame_rate(first.frame_rate).set_channels(first.channels).set_sample_width(first.sample_width)
        segments.append(seg)
        
    res = segments[0]
    for s in segments[1:]:
        res += s
    return res

def normalize_loudness(seg: AudioSegment, target_dbfs: float) -> AudioSegment:
    if seg.dBFS == float("-inf"): return seg
    gain = target_dbfs - seg.dBFS
    return seg.apply_gain(min(gain, -seg.max_dBFS))

def export_segment(seg: AudioSegment, path: Path, fmt: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    seg.export(path, format=fmt)
    return path

def export_book(chapters: list[AudioSegment], cfg: dict[str, Any], out_path: Path) -> Path:
    if not chapters:
        return export_segment(AudioSegment.empty(), out_path, cfg["tts"]["format"])

    first = chapters[0]
    gap = AudioSegment.silent(
        duration=cfg["audio"]["silence_ms_between_chapters"],
        frame_rate=first.frame_rate
    ).set_channels(first.channels).set_sample_width(first.sample_width)
    
    segments = [first]
    for ch in chapters[1:]:
        segments.append(gap)
        ch = ch.set_frame_rate(first.frame_rate).set_channels(first.channels).set_sample_width(first.sample_width)
        segments.append(ch)
        
    book = segments[0]
    for s in segments[1:]:
        book += s
    book = normalize_loudness(book, cfg["audio"]["target_dbfs"])
    return export_segment(book, out_path, cfg["tts"]["format"])
