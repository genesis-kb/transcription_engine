import json
import os
from pathlib import Path
from typing import Any
import yaml
from dotenv import load_dotenv

def load_audiobook_config() -> tuple[dict[str, Any], dict[str, str]]:
    load_dotenv()
    current_dir = Path(__file__).resolve().parent.parent
    config_path = current_dir / "audiobook_config.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        cfg = {}

    # Resolve lexicon path from config, falling back to default
    lexicon_filename = (cfg.get("paths") or {}).get("lexicon", "audiobook_lexicon.json")
    lexicon_path = current_dir / lexicon_filename

    cfg["keys"] = {
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "deepgram": os.getenv("DEEPGRAM_API_KEY", ""),
        "smallest": os.getenv("SMALLEST_API_KEY", ""),
    }

    with open(lexicon_path, "r", encoding="utf-8") as f:
        data = json.loads(f.read())
        if not isinstance(data, dict):
            data = {}
        lexicon = {k: v for k, v in data.items() if not k.startswith("_")}
        
    return cfg, lexicon
