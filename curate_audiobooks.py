"""CLI entry point for the audiobook curation pipeline.

Usage:
    # Process all files in input/audiobooks/
    python curate_audiobooks.py

    # Process files in a custom directory
    python curate_audiobooks.py --input-dir path/to/files

    # Skip the LLM rewrite step (faster, cheaper)
    python curate_audiobooks.py --skip-llm

    # Use a specific TTS provider
    python curate_audiobooks.py --provider smallest
"""
import argparse
import sys
from pathlib import Path

from app.services.audiobook.curator import AudiobookCurator


def main():
    parser = argparse.ArgumentParser(
        description="Curate audiobook playlists from text files."
    )
    parser.add_argument(
        "--input-dir",
        default="input/audiobooks",
        help="Directory containing .txt files (default: input/audiobooks)",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip the OpenAI LLM rewrite/chapterization step",
    )
    parser.add_argument(
        "--provider",
        choices=["deepgram", "smallest"],
        default=None,
        help="Override the TTS provider from config",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=5000,
        help="Word count above which single articles are chapterized "
             "via LLM (default: 5000)",
    )
    parser.add_argument(
        "--diarize",
        action="store_true",
        help="Enable dynamic multi-speaker diarization",
    )
    args = parser.parse_args()

    # Validate input directory before proceeding
    input_path = Path(args.input_dir)
    if not input_path.is_dir():
        print(f"\n  ✗ Input directory does not exist: {input_path}")
        sys.exit(1)

    print(f"{'='*60}")
    print(f"  Audiobook Curation Pipeline")
    print(f"{'='*60}")
    print(f"  Input dir  : {args.input_dir}")
    print(f"  Skip LLM   : {args.skip_llm}")
    print(f"  Diarize    : {args.diarize}")
    print(f"  TTS provider: {args.provider or '(from config)'}")
    print(f"  Chapterize threshold: {args.threshold} words")
    print(f"{'='*60}\n")

    curator = AudiobookCurator(
        chapterize_threshold=args.threshold,
        skip_llm=args.skip_llm,
        provider_override=args.provider,
        diarize=args.diarize,
    )

    result = curator.curate_from_directory(args.input_dir)

    print(f"\n{'='*60}")
    print(f"  Results")
    print(f"{'='*60}")
    print(f"  Episodes generated : {result['episodes_generated']}")
    print(f"  Playlists touched  : {result['playlists_touched']}")
    print(f"  Errors             : {len(result['errors'])}")

    if result["errors"]:
        print(f"\n  Errors:")
        for err in result["errors"]:
            print(f"    ✗ {err}")

    if result["success"]:
        print(f"\n  ✅ Pipeline completed successfully!")
    else:
        print(f"\n  ⚠️  Pipeline completed with errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
