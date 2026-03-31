#!/usr/bin/env python3
"""
podcast_to_mp3.py
-----------------
Convert a podcast script (markdown) to an MP3 file using Google Text-to-Speech
(gTTS), then upload the resulting file to a Dropbox folder.

Usage:
    python podcast_to_mp3.py --script <path> --output <path> [--dropbox-folder <folder>]

Environment variables (or .env file in the same directory as this script):
    DROPBOX_ACCESS_TOKEN   Required. Dropbox API access token.
    DROPBOX_FOLDER         Optional. Destination folder in Dropbox (default: /Podcasts).
"""

import argparse
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional .env loading (no external dependency required)
# ---------------------------------------------------------------------------

def _load_dotenv(env_path: Path) -> None:
    """Load key=value pairs from a .env file into os.environ (if the file exists)."""
    if not env_path.is_file():
        return
    with env_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


# Load .env from the skills/ directory (same dir as this script)
_load_dotenv(Path(__file__).parent / ".env")


# ---------------------------------------------------------------------------
# Script text extraction
# ---------------------------------------------------------------------------

# Lines / patterns that are production cues, not spoken aloud
_CUE_PATTERNS = re.compile(
    r"^\s*(\[MUSIC[^\]]*\]|\[PAUSE\]|\[AD BREAK\]|##|---|#\s)",
    re.IGNORECASE,
)
_HOST_PREFIX = re.compile(r"^\[HOST\]\s*", re.IGNORECASE)


def extract_spoken_text(script_path: Path) -> str:
    """
    Read a podcast script markdown file and return only the spoken text.

    Rules:
    - Lines matching production cues are discarded.
    - Lines starting with [HOST] have the prefix stripped and are kept.
    - All other non-empty lines are kept as-is (e.g. plain paragraph text).
    """
    lines: list[str] = []
    with script_path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if _CUE_PATTERNS.match(line):
                continue
            # Strip [HOST] label if present
            line = _HOST_PREFIX.sub("", line)
            if line:
                lines.append(line)
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Text-to-speech (gTTS)
# ---------------------------------------------------------------------------

def text_to_mp3(text: str, output_path: Path, lang: str = "en") -> None:
    """Convert *text* to an MP3 file at *output_path* using gTTS."""
    try:
        from gtts import gTTS  # type: ignore[import]
    except ImportError:
        sys.exit(
            "❌  gTTS is not installed. Run: pip install gtts"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(str(output_path))
    print(f"✅ MP3 saved locally: {output_path}")


# ---------------------------------------------------------------------------
# Dropbox upload
# ---------------------------------------------------------------------------

def upload_to_dropbox(local_path: Path, dropbox_folder: str, token: str) -> str:
    """
    Upload *local_path* to Dropbox under *dropbox_folder*.

    Returns the full Dropbox destination path.
    """
    try:
        import dropbox  # type: ignore[import]
        from dropbox.exceptions import ApiError, AuthError  # type: ignore[import]
        from dropbox.files import WriteMode  # type: ignore[import]
    except ImportError:
        sys.exit(
            "❌  dropbox SDK is not installed. Run: pip install dropbox"
        )

    # Normalize the destination path
    folder = dropbox_folder.rstrip("/")
    if not folder.startswith("/"):
        folder = "/" + folder
    dest = f"{folder}/{local_path.name}"

    dbx = dropbox.Dropbox(token)

    # Verify the token is valid before attempting the upload
    try:
        dbx.users_get_current_account()
    except AuthError:
        sys.exit(
            "❌  Invalid Dropbox access token. Check DROPBOX_ACCESS_TOKEN in skills/.env"
        )

    with local_path.open("rb") as fh:
        try:
            dbx.files_upload(fh.read(), dest, mode=WriteMode("overwrite"), mute=True)
        except ApiError as exc:
            sys.exit(f"❌  Dropbox upload failed: {exc}")

    print(f"✅ Uploaded to Dropbox: {dest}")
    return dest


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a podcast script to MP3 and upload to Dropbox."
    )
    parser.add_argument(
        "--script",
        required=True,
        help="Path to the podcast script markdown file.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Destination path for the generated MP3 file.",
    )
    parser.add_argument(
        "--dropbox-folder",
        default=os.environ.get("DROPBOX_FOLDER", "/Podcasts"),
        help="Dropbox folder to upload the MP3 to (default: /Podcasts).",
    )
    parser.add_argument(
        "--lang",
        default="en",
        help="BCP 47 language code for text-to-speech (default: en).",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip the Dropbox upload step (useful for local testing).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    script_path = Path(args.script)
    if not script_path.is_file():
        sys.exit(f"❌  Script file not found: {script_path}")

    output_path = Path(args.output)

    # --- Extract spoken text ---
    print(f"📄 Reading script: {script_path}")
    text = extract_spoken_text(script_path)
    if not text.strip():
        sys.exit("❌  No spoken text found in the script. Nothing to convert.")

    word_count = len(text.split())
    approx_minutes = round(word_count / 130, 1)
    print(f"📝 {word_count} words extracted (~{approx_minutes} min at 130 wpm)")

    # --- TTS conversion ---
    text_to_mp3(text, output_path, lang=args.lang)

    # --- Dropbox upload ---
    if args.no_upload:
        print("⏭️  Skipping Dropbox upload (--no-upload flag set).")
        return

    token = os.environ.get("DROPBOX_ACCESS_TOKEN", "")
    if not token:
        sys.exit(
            "❌  DROPBOX_ACCESS_TOKEN is not set.\n"
            "    Add it to skills/.env or export it as an environment variable.\n"
            "    See skills/README.md for setup instructions."
        )

    upload_to_dropbox(output_path, args.dropbox_folder, token)


if __name__ == "__main__":
    main()
