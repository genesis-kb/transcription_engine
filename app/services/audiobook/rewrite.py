import json
from typing import Any
from openai import OpenAI

SYSTEM = """You are an audiobook editor. You turn raw text/transcripts into a \
clean narration script meant to be READ ALOUD.

Rules:
- Remove filler words, false starts, and repetition. Keep the meaning and voice.
- Rewrite spoken fragments into smooth, complete sentences.
- Split the content into logical chapters with short descriptive titles.
- Write a one-sentence intro line at the start of chapter 1 if helpful.
- Do NOT add facts that aren't in the source.
- Output ONLY valid JSON, no markdown fences."""

USER_TMPL = """Convert the following into an audiobook script.

Return JSON exactly like:
{{"title": "<book title>", "chapters": [{{"title": "<chapter title>", "text": "<narration>"}}]}}

SOURCE:
\"\"\"
{source}
\"\"\""""

def rewrite(text: str, cfg: dict[str, Any]) -> dict[str, Any]:
    client = OpenAI(api_key=cfg["keys"].get("openai", ""))
    resp = client.chat.completions.create(
        model=cfg["llm"]["model"],
        temperature=cfg["llm"]["temperature"],
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_TMPL.format(source=text)},
        ],
    )
    try:
        content = resp.choices[0].message.content
        if not content:
            manifest = {}
        else:
            manifest = json.loads(content)
            if not isinstance(manifest, dict):
                manifest = {}
    except (IndexError, AttributeError, ValueError, json.JSONDecodeError):
        manifest = {}

    manifest.setdefault("title", "Untitled Audiobook")
    
    chapters = manifest.get("chapters", [])
    if not isinstance(chapters, list):
        chapters = []
        
    valid_chapters = []
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        title = ch.get("title")
        text_val = ch.get("text")
        # Coerce non-string values; skip entries that are None or non-stringable
        if title is None or text_val is None:
            continue
        if not isinstance(title, str):
            title = str(title)
        if not isinstance(text_val, str):
            text_val = str(text_val)
        if not title.strip():
            continue
        if not text_val.strip():
            continue
        valid_chapters.append({"title": title.strip(), "text": text_val.strip()})
            
    manifest["chapters"] = valid_chapters
    return manifest
