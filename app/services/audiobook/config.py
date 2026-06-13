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
    lexicon_path = current_dir / "audiobook_lexicon.json"

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg["keys"] = {
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "deepgram": os.getenv("DEEPGRAM_API_KEY", ""),
        "smallest": os.getenv("SMALLEST_API_KEY", ""),
    }

    with open(lexicon_path, "r", encoding="utf-8") as f:
        data = json.loads(f.read())
        lexicon = {k: v for k, v in data.items() if not k.startswith("_")}
        
    return cfg, lexicon
