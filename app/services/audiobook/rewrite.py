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
    manifest = json.loads(resp.choices[0].message.content)
    manifest.setdefault("title", "Untitled Audiobook")
    manifest.setdefault("chapters", [])
    return manifest
