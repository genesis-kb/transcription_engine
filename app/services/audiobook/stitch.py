import io
from pathlib import Path
from typing import Any
from pydub import AudioSegment

def _seg(audio: bytes, fmt: str) -> AudioSegment:
    return AudioSegment.from_file(io.BytesIO(audio), format=fmt)

def _coerce(seg: AudioSegment, ref: AudioSegment) -> AudioSegment:
    """Normalize *seg* to match *ref*'s sample rate, channels, and sample width."""
    if seg.frame_rate != ref.frame_rate:
        seg = seg.set_frame_rate(ref.frame_rate)
    if seg.channels != ref.channels:
        seg = seg.set_channels(ref.channels)
    if seg.sample_width != ref.sample_width:
        seg = seg.set_sample_width(ref.sample_width)
    return seg

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
        segments.append(_coerce(_seg(c, fmt), first))
        
    return first._spawn(b"".join(s.raw_data for s in segments))

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

    # Find the first non-empty chapter to use as the reference for audio params.
    # An empty first chapter would otherwise produce corrupt metadata.
    ref = None
    for ch in chapters:
        if len(ch) > 0:
            ref = ch
            break
    if ref is None:
        return export_segment(AudioSegment.empty(), out_path, cfg["tts"]["format"])

    gap = AudioSegment.silent(
        duration=cfg["audio"]["silence_ms_between_chapters"],
        frame_rate=ref.frame_rate
    ).set_channels(ref.channels).set_sample_width(ref.sample_width)
    
    segments = [_coerce(chapters[0], ref)]
    for ch in chapters[1:]:
        segments.append(gap)
        segments.append(_coerce(ch, ref))
        
    book = ref._spawn(b"".join(s.raw_data for s in segments))
    book = normalize_loudness(book, cfg["audio"]["target_dbfs"])
    return export_segment(book, out_path, cfg["tts"]["format"])
