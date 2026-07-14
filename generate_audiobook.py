"""Generate a single audiobook from a text file (legacy CLI).

For the full playlist-aware curation pipeline, use curate_audiobooks.py
instead.

Usage:
    python generate_audiobook.py sample_bitcoin.txt
    python generate_audiobook.py sample_bitcoin.txt --skip-llm
"""
import argparse

from app.services.audiobook_service import AudiobookService


def main():
    parser = argparse.ArgumentParser(
        description="Generate an audiobook from a text file."
    )
    parser.add_argument("input", help="path to a .txt transcript")
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Bypass the OpenAI rewrite step",
    )
    parser.add_argument(
        "--diarize",
        action="store_true",
        help="Enable dynamic multi-speaker diarization",
    )
    args = parser.parse_args()

    print(f"Reading file: {args.input}...")
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            text = f.read()
            if not text.strip():
                print(f"❌ Error: File '{args.input}' is empty.")
                raise SystemExit(1)
    except FileNotFoundError:
        print(f"❌ Error: File '{args.input}' not found.")
        raise SystemExit(1)

    print("Initializing Audiobook Service...")
    service = AudiobookService()

    print(
        "Generating audiobook... "
        "(This may take a minute depending on TTS and LLM speeds)"
    )
    result = service.generate_from_text(text=text, skip_llm=args.skip_llm, diarize=args.diarize)

    if result:
        print(f"\n✅ Success!")
        print(f"Title: {result['title']}")
        print(f"Audio File Saved To: {result['audio_url']}")
        print(f"Duration: {result['duration_seconds']}s")
    else:
        print("\n❌ Failed to generate audiobook.")


if __name__ == "__main__":
    main()
