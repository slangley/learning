#!/usr/bin/env python3
"""
podcast_to_mp3.py
-----------------
Convert a podcast script (markdown) to an MP3 file using ElevenLabs text-to-speech,
then upload the resulting file to an S3 bucket.

Usage:
    python podcast_to_mp3.py --script <path> --output <path> [--s3-bucket <bucket>] [--s3-prefix <prefix>]

Environment variables (or .env file in the same directory as this script):
    ELEVENLABS_API_KEY     Required. ElevenLabs API key.
    S3_BUCKET              Required. S3 bucket name.
    S3_PREFIX              Optional. Key prefix inside the bucket (default: podcasts/).
    AWS_ACCESS_KEY_ID      Optional. Falls back to ~/.aws/credentials or IAM role.
    AWS_SECRET_ACCESS_KEY  Optional. Falls back to ~/.aws/credentials or IAM role.
    AWS_REGION             Optional. AWS region (default: us-east-1).
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
# Text-to-speech (ElevenLabs)
# ---------------------------------------------------------------------------

DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # George
DEFAULT_MODEL_ID = "eleven_turbo_v2_5"


def text_to_mp3(
    text: str,
    output_path: Path,
    voice_id: str = DEFAULT_VOICE_ID,
    model_id: str = DEFAULT_MODEL_ID,
) -> None:
    """Convert *text* to an MP3 file at *output_path* using ElevenLabs."""
    try:
        from elevenlabs import ElevenLabs  # type: ignore[import]
    except ImportError:
        sys.exit(
            "❌  elevenlabs is not installed. Run: pip install elevenlabs"
        )

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        sys.exit(
            "❌  ELEVENLABS_API_KEY is not set.\n"
            "    Add it to skills/.env or export it as an environment variable.\n"
            "    Get a key at https://elevenlabs.io/app/settings/api-keys"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    client = ElevenLabs(api_key=api_key)
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=model_id,
    )
    with output_path.open("wb") as fh:
        for chunk in audio:
            fh.write(chunk)
    print(f"✅ MP3 saved locally: {output_path}")


# ---------------------------------------------------------------------------
# S3 upload
# ---------------------------------------------------------------------------

def upload_to_s3(local_path: Path, bucket: str, prefix: str) -> str:
    """
    Upload *local_path* to S3 at s3://<bucket>/<prefix><filename>.

    Returns the full S3 URI.
    """
    try:
        import boto3  # type: ignore[import]
        from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import]
    except ImportError:
        sys.exit(
            "❌  boto3 is not installed. Run: pip install boto3"
        )

    prefix = prefix.rstrip("/") + "/" if prefix else ""
    key = f"{prefix}{local_path.name}"

    region = os.environ.get("AWS_REGION", "us-east-1")
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    s3 = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=aws_key,
        aws_secret_access_key=aws_secret,
    )

    try:
        s3.upload_file(str(local_path), bucket, key)
    except (BotoCoreError, ClientError) as exc:
        sys.exit(f"❌  S3 upload failed: {exc}")

    uri = f"s3://{bucket}/{key}"
    print(f"✅ Uploaded to S3: {uri}")
    return uri


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
        "--s3-bucket",
        default=os.environ.get("S3_BUCKET", ""),
        help="S3 bucket name to upload the MP3 to.",
    )
    parser.add_argument(
        "--s3-prefix",
        default=os.environ.get("S3_PREFIX", "podcasts/"),
        help="Key prefix (folder) inside the S3 bucket (default: podcasts/).",
    )
    parser.add_argument(
        "--voice",
        default=DEFAULT_VOICE_ID,
        help=f"ElevenLabs voice ID (default: {DEFAULT_VOICE_ID} — George).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_ID,
        help=f"ElevenLabs model ID (default: {DEFAULT_MODEL_ID}).",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip the S3 upload step (useful for local testing).",
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
    text_to_mp3(text, output_path, voice_id=args.voice, model_id=args.model)

    # --- S3 upload ---
    if args.no_upload:
        print("⏭️  Skipping S3 upload (--no-upload flag set).")
        return

    if not args.s3_bucket:
        sys.exit(
            "❌  S3_BUCKET is not set.\n"
            "    Add it to skills/.env or pass --s3-bucket <bucket>.\n"
            "    See skills/README.md for setup instructions."
        )

    upload_to_s3(output_path, args.s3_bucket, args.s3_prefix)


if __name__ == "__main__":
    main()
