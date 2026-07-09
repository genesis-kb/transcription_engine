import re

try:
    from num2words import num2words
except ImportError:
    num2words = None

TIMESTAMP = re.compile(r"[\[\(]?\b\d{1,2}:\d{2}(?::\d{2})?\b[\]\)]?")
SPEAKER = re.compile(r"^\s*[A-Z][A-Za-z0-9 _-]{0,30}:\s", re.MULTILINE)
STAGE = re.compile(r"[\[\(](?:laughter|music|applause|crosstalk|inaudible)[\]\)]", re.I)
MULTISPACE = re.compile(r"[ \t]{2,}")
MULTINEWLINE = re.compile(r"\n{3,}")

def clean_text(raw: str, retain_speakers: bool = False) -> str:
    text = TIMESTAMP.sub("", raw)
    if not retain_speakers:
        text = SPEAKER.sub("", text)
    text = STAGE.sub("", text)
    text = MULTISPACE.sub(" ", text)
    text = MULTINEWLINE.sub("\n\n", text)
    return text.strip()

def parse_diarization(text: str) -> list[dict]:
    """Splits text into chunks by speaker if speaker tags are present."""
    matches = list(SPEAKER.finditer(text))
    if not matches:
        return [{"speaker": "default", "text": text}]
    
    chunks = []
    if matches[0].start() > 0:
        pre_text = text[:matches[0].start()].strip()
        if pre_text:
            chunks.append({"speaker": "default", "text": pre_text})
            
    for i, match in enumerate(matches):
        speaker_name = match.group(0).strip()[:-1] # Remove colon
        start_idx = match.end()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(text)
        
        spoken_text = text[start_idx:end_idx].strip()
        if spoken_text:
            chunks.append({"speaker": speaker_name, "text": spoken_text})
            
    return chunks

MONEY = re.compile(r"\$\s?(\d[\d,]*\.?\d*)\s?([kKmMbB])?")
_SCALE = {"k": " thousand", "m": " million", "b": " billion"}

def _expand_money(m: re.Match) -> str:
    num = m.group(1).replace(",", "")
    scale = _SCALE.get((m.group(2) or "").lower(), "")
    return f"{num}{scale} dollars"

YEAR = re.compile(r"\b(1[8-9]\d{2}|20\d{2})\b")
ORDINAL = re.compile(r"\b(\d+)(st|nd|rd|th)\b", re.IGNORECASE)
NUMBER = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")
ACRONYM = re.compile(r"\b([A-Z]{2,})(s)?\b")

PRONOUNCEABLE_ACRONYMS = {
    "NASA", "NATO", "FEMA", "OSHA", "AIDS", "MAC", "PIN", "RAM", "ROM", 
    "LAN", "WAN", "FAQ", "GUI", "HUD", "GIF", "JPEG", "OPEC", "UNESCO", "UNICEF"
}

def _expand_year(m: re.Match) -> str:
    if not num2words:
        return m.group(0)
    return num2words(int(m.group(1)), to='year').replace("-", " ")

def _expand_ordinal(m: re.Match) -> str:
    if not num2words:
        return m.group(0)
    return num2words(int(m.group(1)), to='ordinal').replace("-", " ")

def _expand_number(m: re.Match) -> str:
    if not num2words:
        return m.group(0)
    val = m.group(0).replace(",", "")
    try:
        if "." in val:
            return num2words(float(val)).replace("-", " ")
        return num2words(int(val)).replace("-", " ")
    except Exception:
        return m.group(0)

def _expand_acronym(m: re.Match) -> str:
    word = m.group(1)
    plural = m.group(2)
    if word in PRONOUNCEABLE_ACRONYMS:
        return m.group(0)
    expanded = "-".join(word)
    if plural:
        expanded += "-s"
    return expanded

def normalize(text: str) -> str:
    text = MONEY.sub(_expand_money, text)
    
    if num2words:
        text = YEAR.sub(_expand_year, text)
        text = ORDINAL.sub(_expand_ordinal, text)
        text = NUMBER.sub(_expand_number, text)
        
    text = ACRONYM.sub(_expand_acronym, text)
    return text

try:
    import nltk
except ImportError:
    nltk = None

# We use an exhaustive prosody split for long sentences.
PROSODY_SPLIT = re.compile(r'(?<=[;:,\—\-])\s+')
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

def chunk_split(text: str, max_chars: int) -> list[str]:
    if nltk:
        try:
            sentences = nltk.tokenize.sent_tokenize(text.strip())
        except LookupError:
            sentences = SENTENCE_END.split(text.strip())
    else:
        sentences = SENTENCE_END.split(text.strip())
        
    chunks: list[str] = []
    current = ""
    
    for s in sentences:
        if not s: continue
        
        sub_sentences = []
        if len(s) > max_chars:
            parts = PROSODY_SPLIT.split(s)
            sub_sentences.extend(parts)
        else:
            sub_sentences.append(s)
            
        for part in sub_sentences:
            if not part: continue
            
            if len(part) > max_chars:
                for word in part.split():
                    if len(word) > max_chars:
                        # Word itself exceeds limit — split at character level
                        if current.strip():
                            chunks.append(current.strip())
                            current = ""
                        for i in range(0, len(word), max_chars):
                            chunks.append(word[i:i + max_chars])
                    elif len(current) + len(word) + 1 > max_chars:
                        if current.strip():
                            chunks.append(current.strip())
                        current = word
                    else:
                        current = f"{current} {word}".strip() if current else word
                continue
                
            if len(current) + len(part) + 1 > max_chars:
                if current.strip():
                    chunks.append(current.strip())
                current = part
            else:
                current = f"{current} {part}".strip() if current else part
                
    if current.strip():
        chunks.append(current.strip())
        
    return chunks
