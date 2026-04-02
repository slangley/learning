#!/usr/bin/env python3
"""
podcast_to_mp3.py
-----------------
Convert a podcast script (markdown) to an MP3 file using ElevenLabs text-to-speech,
with support for multi-voice ad segments, intro/outro music, and episode metadata.

Usage:
    python podcast_to_mp3.py --script <path> --output <path> [options]

Environment variables (or .env file in the same directory as this script):
    ELEVENLABS_API_KEY     Required. ElevenLabs API key.
    S3_BUCKET              Required. S3 bucket name.
    S3_PREFIX              Optional. Key prefix inside the bucket (default: episodes/).
    AWS_ACCESS_KEY_ID      Optional. Falls back to ~/.aws/credentials or IAM role.
    AWS_SECRET_ACCESS_KEY  Optional. Falls back to ~/.aws/credentials or IAM role.
    AWS_REGION             Optional. AWS region (default: us-east-1).
"""

import argparse
import io
import os
import re
import shutil
import sys
import tempfile
from datetime import date
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
# Voice & model constants
# ---------------------------------------------------------------------------

VOICES = {
    "george":  "JBFqnCBsd6RMkjVDRZzb",
    "rachel":  "cgSgspJ2msm6clMCkdW9",   # Jessica - Playful, Bright, Warm
    "dave":    "iP95p4xoKVk53GoZ742B",   # Chris - Charming, Down-to-Earth
    "josh":    "TxGEqnHWrfWFTfGW9XjX",
    "adam":    "pNInz6obpgDQGcFmaJgB",
    "sam":     "yoZ06aMxZJJ28mfd3POQ",
    "sarah":   "EXAVITQu4vr4xnSDxMaL",
    "brian":   "nPczCjzI2devNBz1zQrb",
    "lily":    "pFZP5JQG7iQjIQuC4Bku",
    "matilda": "XrExE9yKIg1WjnnlVkGX",
    "antoni":  "ErXwobaYiN019PkySvjV",
    "arnold":  "VR6AewLTigWG4xSOukaG",
    "domi":    "AZnzlk1XvdvUeBnXmlld",
}

DEFAULT_VOICE = "george"
DEFAULT_MODEL_ID = "eleven_v3"

ASSETS_DIR = Path(__file__).parent.parent / "podcast-assets"

SFX_PROMPTS = {
    "intro": ("upbeat podcast intro jingle, energetic and modern", 8.0),
    "outro": ("mellow podcast outro music, smooth fade out", 6.0),
}

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

def preflight() -> None:
    """Verify required tools and credentials are available."""
    if not shutil.which("ffmpeg"):
        sys.exit(
            "❌  ffmpeg is not installed. pydub requires ffmpeg for audio processing.\n"
            "    Install it with: apt-get install ffmpeg  (or brew install ffmpeg on macOS)"
        )
    if not os.environ.get("ELEVENLABS_API_KEY"):
        sys.exit(
            "❌  ELEVENLABS_API_KEY is not set.\n"
            "    Add it to skills/.env or export it as an environment variable.\n"
            "    Get a key at https://elevenlabs.io/app/settings/api-keys"
        )


def _get_client():
    """Return a configured ElevenLabs client."""
    try:
        from elevenlabs import ElevenLabs  # type: ignore[import]
    except ImportError:
        sys.exit("❌  elevenlabs is not installed. Run: pip install elevenlabs")
    return ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])


# ---------------------------------------------------------------------------
# Segment-aware script parser
# ---------------------------------------------------------------------------

_MUSIC_INTRO = re.compile(r"^\s*\*?\[MUSIC\s*-\s*INTRO\]\*?\s*$", re.IGNORECASE)
_MUSIC_OUTRO = re.compile(r"^\s*\*?\[MUSIC\s*-\s*(OUTRO|FADE\s*OUT)\]\*?\s*$", re.IGNORECASE)
_PAUSE = re.compile(r"^\s*\*?\[PAUSE\]\*?\s*$", re.IGNORECASE)
_AD_BREAK = re.compile(r"^\s*\*?\[AD\s+BREAK\]\*?\s*$", re.IGNORECASE)
_AD_END = re.compile(r"^\s*\*?\[AD\s+END\]\*?\s*$", re.IGNORECASE)
_HOST_PREFIX = re.compile(r"^\[HOST\]\s*", re.IGNORECASE)
_VOICE_PREFIX = re.compile(r"^\[VOICE:(\w+)\]\s*", re.IGNORECASE)
_HEADING = re.compile(r"^\s*(###|##|---|#\s)")
_SOURCES_SECTION = re.compile(r"^\s*#{1,3}\s*Sources?\s*$", re.IGNORECASE)
_NUMBERED_ITEM = re.compile(r"^\s*\d+\.\s")
_SOURCE_CITATION = re.compile(r"\s*\(Source:\s*([^)]+)\)")


def resolve_voice_id(name_or_id: str) -> str:
    """Resolve a voice name to its ElevenLabs ID, or pass through raw IDs."""
    lower = name_or_id.lower()
    if lower in VOICES:
        return VOICES[lower]
    return name_or_id


def parse_script(script_path: Path, host_voice: str) -> tuple[list[dict], list[dict]]:
    """
    Parse a podcast script into an ordered list of typed segments.

    Returns (segments, sources) where sources is a list of
    {"name": ..., "date": ..., "context": ...} dicts extracted from citations.
    """
    segments: list[dict] = []
    sources: list[dict] = []
    in_ad = False
    in_sources_section = False
    ad_lines: list[dict] = []
    host_lines: list[str] = []

    def flush_host():
        nonlocal host_lines
        if host_lines:
            text = " ".join(host_lines)
            segments.append({"type": "speech", "voice": host_voice, "text": text})
            host_lines = []

    def flush_ad():
        nonlocal ad_lines, in_ad
        if ad_lines:
            # Prepend [ding] to first line, append [ding] to last line
            ad_lines[0]["text"] = "[ding] " + ad_lines[0]["text"]
            ad_lines[-1]["text"] = ad_lines[-1]["text"] + " [ding]"
            segments.append({"type": "ad", "lines": list(ad_lines)})
            ad_lines = []
        in_ad = False

    def strip_sources(text: str) -> str:
        """Strip (Source: ...) citations from text, collecting them into sources list."""
        for match in _SOURCE_CITATION.finditer(text):
            raw = match.group(1).strip()
            # Split on first comma: "CBC News, March 31, 2026" → name="CBC News", date="March 31, 2026"
            parts = [p.strip() for p in raw.split(",", 1)]
            if len(parts) == 2:
                sources.append({"name": parts[0], "date": parts[1], "context": ""})
            else:
                sources.append({"name": raw, "date": "", "context": ""})
        return _SOURCE_CITATION.sub("", text).strip()

    with script_path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue

            # Sources section at end of script — skip all remaining lines
            if _SOURCES_SECTION.match(line):
                flush_host()
                in_sources_section = True
                continue
            if in_sources_section:
                continue

            # Music cues
            if _MUSIC_INTRO.match(line):
                flush_host()
                segments.append({"type": "music", "asset": "intro"})
                continue
            if _MUSIC_OUTRO.match(line):
                flush_host()
                segments.append({"type": "music", "asset": "outro"})
                continue

            # Pause
            if _PAUSE.match(line):
                flush_host()
                segments.append({"type": "pause", "duration_ms": 1000})
                continue

            # Ad break markers
            if _AD_BREAK.match(line):
                flush_host()
                in_ad = True
                continue
            if _AD_END.match(line):
                flush_ad()
                continue

            # Headings / markdown separators — skip
            if _HEADING.match(line):
                continue

            # Inside ad block — look for [VOICE:name] lines
            if in_ad:
                vm = _VOICE_PREFIX.match(line)
                if vm:
                    voice_name = vm.group(1)
                    text = strip_sources(line[vm.end():])
                    if text:
                        ad_lines.append({
                            "voice": resolve_voice_id(voice_name),
                            "text": text,
                        })
                else:
                    # Bare line inside ad — use first ad voice or host
                    text = strip_sources(_HOST_PREFIX.sub("", line))
                    if text:
                        fallback_voice = ad_lines[-1]["voice"] if ad_lines else resolve_voice_id(host_voice)
                        ad_lines.append({"voice": fallback_voice, "text": text})
                continue

            # Host line
            hm = _HOST_PREFIX.match(line)
            if hm:
                text = strip_sources(line[hm.end():])
                if text:
                    host_lines.append(text)
                continue

            # Any other non-empty line (plain text) — treat as host speech
            text = strip_sources(line)
            if text and not line.startswith("*") and not line.startswith("["):
                host_lines.append(text)

    # Flush remaining
    flush_host()
    if in_ad:
        flush_ad()

    return segments, sources


# ---------------------------------------------------------------------------
# Audio generation
# ---------------------------------------------------------------------------

def generate_speech(text: str, voice_id: str, model_id: str, output_path: Path) -> None:
    """Generate single-voice speech MP3."""
    client = _get_client()
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=model_id,
        output_format="mp3_44100_128",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        for chunk in audio:
            fh.write(chunk)


def generate_dialogue(lines: list[dict], model_id: str, output_path: Path) -> None:
    """Generate multi-voice dialogue MP3 using the Text to Dialogue API."""
    from elevenlabs.types import DialogueInput

    client = _get_client()
    inputs = [DialogueInput(text=ln["text"], voice_id=ln["voice"]) for ln in lines]
    audio = client.text_to_dialogue.convert(
        inputs=inputs,
        model_id=model_id,
        output_format="mp3_44100_128",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        for chunk in audio:
            fh.write(chunk)


def generate_or_load_asset(asset_name: str) -> Path:
    """
    Return path to a cached audio asset, generating it via SFX API if missing.
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    asset_path = ASSETS_DIR / f"{asset_name}.mp3"
    if asset_path.is_file():
        print(f"  Cached asset: {asset_path}")
        return asset_path

    if asset_name not in SFX_PROMPTS:
        sys.exit(f"❌  Unknown asset: {asset_name}. Expected one of: {list(SFX_PROMPTS.keys())}")

    prompt, duration = SFX_PROMPTS[asset_name]
    print(f"  Generating SFX asset '{asset_name}' ({duration}s)...")
    client = _get_client()
    audio = client.text_to_sound_effects.convert(
        text=prompt,
        duration_seconds=duration,
        output_format="mp3_44100_128",
    )
    with asset_path.open("wb") as fh:
        for chunk in audio:
            fh.write(chunk)
    print(f"  Saved asset: {asset_path}")
    return asset_path


# ---------------------------------------------------------------------------
# Audio assembly
# ---------------------------------------------------------------------------

def assemble_podcast(segments: list[dict], model_id: str, tmp_dir: Path) -> bytes:
    """
    Generate audio for each segment and concatenate into a single MP3.

    Returns the final MP3 as bytes.
    """
    from pydub import AudioSegment

    parts: list[AudioSegment] = []
    seg_idx = 0

    for seg in segments:
        stype = seg["type"]

        if stype == "music":
            asset_path = generate_or_load_asset(seg["asset"])
            parts.append(AudioSegment.from_mp3(str(asset_path)))
            print(f"  [{seg_idx}] Music: {seg['asset']}")

        elif stype == "pause":
            ms = seg.get("duration_ms", 1000)
            parts.append(AudioSegment.silent(duration=ms))
            print(f"  [{seg_idx}] Pause: {ms}ms")

        elif stype == "speech":
            seg_path = tmp_dir / f"seg_{seg_idx:03d}_speech.mp3"
            word_count = len(seg["text"].split())
            print(f"  [{seg_idx}] Speech: {word_count} words (voice: {seg['voice']})")
            generate_speech(seg["text"], resolve_voice_id(seg["voice"]), model_id, seg_path)
            parts.append(AudioSegment.from_mp3(str(seg_path)))

        elif stype == "ad":
            seg_path = tmp_dir / f"seg_{seg_idx:03d}_ad.mp3"
            voices_used = set(ln["voice"] for ln in seg["lines"])
            print(f"  [{seg_idx}] Ad: {len(seg['lines'])} lines, {len(voices_used)} voice(s)")
            generate_dialogue(seg["lines"], model_id, seg_path)
            parts.append(AudioSegment.from_mp3(str(seg_path)))

        seg_idx += 1

    if not parts:
        sys.exit("❌  No audio segments generated.")

    # Concatenate all parts
    combined = parts[0]
    for part in parts[1:]:
        combined += part

    # Export to bytes
    buf = io.BytesIO()
    combined.export(buf, format="mp3", bitrate="128k")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Episode metadata YAML
# ---------------------------------------------------------------------------

def extract_title(script_path: Path) -> str:
    """Extract the H1 title from the script markdown."""
    with script_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("# ") and not line.startswith("##"):
                return line[2:].strip()
    return script_path.stem.replace("-", " ").title()


def build_transcript(segments: list[dict]) -> str:
    """Build a clean transcript from segments (no audio tags)."""
    audio_tag = re.compile(r"\[[\w\s-]+\]\s*")
    lines = []
    for seg in segments:
        if seg["type"] == "speech":
            clean = audio_tag.sub("", seg["text"]).strip()
            if clean:
                lines.append(clean)
        elif seg["type"] == "ad":
            lines.append("[Ad Break]")
            for ln in seg["lines"]:
                clean = audio_tag.sub("", ln["text"]).strip()
                if clean:
                    lines.append(f"  {clean}")
            lines.append("[End Ad Break]")
    return "\n".join(lines)


def generate_episode_yaml(
    script_path: Path,
    output_mp3: Path,
    segments: list[dict],
    sources: list[dict],
    s3_uris: dict[str, str],
    duration_seconds: float,
) -> Path:
    """Generate episode metadata YAML file."""
    import yaml

    episodes_dir = Path("podcast-episodes")
    episodes_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = episodes_dir / (script_path.stem + ".yaml")

    # Duration formatting
    mins = int(duration_seconds // 60)
    secs = int(duration_seconds % 60)
    duration_str = f"{mins}:{secs:02d}"

    title = extract_title(script_path)

    # Extract date from filename (expects ...-YYYY-MM-DD.md)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", script_path.stem)
    ep_date = date_match.group(1) if date_match else str(date.today())

    transcript = build_transcript(segments)

    # Word count from transcript
    word_count = len(transcript.split())

    episode = {
        "title": title,
        "date": ep_date,
        "duration": duration_str,
        "word_count": word_count,
        "summary": f"Episode generated from {script_path.name}",
        "transcript": transcript,
        "sources": sources if sources else [],
        "audio_file": str(output_mp3),
        "s3_uri": s3_uris.get("mp3", ""),
        "s3_script_uri": s3_uris.get("script", ""),
        "s3_metadata_uri": s3_uris.get("metadata", ""),
    }

    with yaml_path.open("w", encoding="utf-8") as fh:
        yaml.dump(episode, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"📋 Episode metadata: {yaml_path}")
    return yaml_path


# ---------------------------------------------------------------------------
# S3 upload
# ---------------------------------------------------------------------------

def upload_to_s3(local_path: Path, bucket: str, prefix: str) -> str:
    """Upload *local_path* to S3. Returns the full S3 URI."""
    try:
        import boto3  # type: ignore[import]
        from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import]
    except ImportError:
        sys.exit("❌  boto3 is not installed. Run: pip install boto3")

    prefix = prefix.rstrip("/") + "/" if prefix else ""
    key = f"{prefix}{local_path.name}"

    region = os.environ.get("AWS_REGION", "us-east-1")
    s3 = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
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
    voice_names = ", ".join(VOICES.keys())
    parser = argparse.ArgumentParser(
        description="Convert a podcast script to MP3 with multi-voice support."
    )
    parser.add_argument(
        "--script", required=True,
        help="Path to the podcast script markdown file.",
    )
    parser.add_argument(
        "--output", required=True,
        help="Destination path for the generated MP3 file.",
    )
    parser.add_argument(
        "--s3-bucket",
        default=os.environ.get("S3_BUCKET", ""),
        help="S3 bucket name.",
    )
    parser.add_argument(
        "--s3-prefix",
        default=os.environ.get("S3_PREFIX", "episodes/"),
        help="Key prefix inside the S3 bucket (default: episodes/).",
    )
    parser.add_argument(
        "--host-voice", "--voice",
        default=DEFAULT_VOICE, dest="host_voice",
        help=f"Host voice name or ID. Available: {voice_names} (default: {DEFAULT_VOICE}).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_ID,
        help=f"ElevenLabs model ID (default: {DEFAULT_MODEL_ID}).",
    )
    parser.add_argument(
        "--no-music", action="store_true",
        help="Skip intro/outro music jingles.",
    )
    parser.add_argument(
        "--no-upload", action="store_true",
        help="Skip the S3 upload step.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    preflight()

    script_path = Path(args.script)
    if not script_path.is_file():
        sys.exit(f"❌  Script file not found: {script_path}")

    output_path = Path(args.output)

    # --- Resolve host voice ---
    host_voice = args.host_voice.lower()
    host_voice_id = resolve_voice_id(host_voice)
    print(f"📄 Script:  {script_path}")
    print(f"🎙️  Host:    {host_voice} ({host_voice_id})")
    print(f"🤖 Model:   {args.model}")

    # --- Parse script into segments ---
    print("\n🔍 Parsing script...")
    segments, sources = parse_script(script_path, host_voice)

    # Filter out music segments if --no-music
    if args.no_music:
        segments = [s for s in segments if s["type"] != "music"]
        print("  (music segments skipped due to --no-music)")

    # Count stats
    speech_words = sum(
        len(s["text"].split()) for s in segments if s["type"] == "speech"
    )
    ad_count = sum(1 for s in segments if s["type"] == "ad")
    music_count = sum(1 for s in segments if s["type"] == "music")
    print(f"  {len(segments)} segments: {speech_words} spoken words, {ad_count} ad(s), {music_count} music cue(s)")
    print(f"  {len(sources)} source citation(s) extracted")

    # --- Generate & assemble audio ---
    print("\n🎵 Generating audio...")
    with tempfile.TemporaryDirectory(prefix="podcast_") as tmp:
        tmp_dir = Path(tmp)
        mp3_bytes = assemble_podcast(segments, args.model, tmp_dir)

    # Write final MP3
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(mp3_bytes)

    # Calculate duration
    from pydub import AudioSegment as _AS
    final_audio = _AS.from_mp3(str(output_path))
    duration_secs = len(final_audio) / 1000.0
    mins = int(duration_secs // 60)
    secs = int(duration_secs % 60)
    print(f"\n✅ MP3 saved: {output_path} ({mins}:{secs:02d})")

    # --- S3 uploads ---
    s3_uris: dict[str, str] = {}
    if not args.no_upload:
        if not args.s3_bucket:
            sys.exit(
                "❌  S3_BUCKET is not set.\n"
                "    Add it to skills/.env or pass --s3-bucket <bucket>."
            )
        s3_uris["mp3"] = upload_to_s3(output_path, args.s3_bucket, "episodes/")
        s3_uris["script"] = upload_to_s3(script_path, args.s3_bucket, "scripts/")
    else:
        print("⏭️  Skipping S3 upload (--no-upload flag set).")

    # --- Episode metadata YAML ---
    yaml_path = generate_episode_yaml(
        script_path, output_path, segments, sources, s3_uris, duration_secs,
    )

    # Upload YAML to S3 too
    if not args.no_upload and args.s3_bucket:
        s3_uris["metadata"] = upload_to_s3(yaml_path, args.s3_bucket, "metadata/")
        # Update the YAML with the metadata URI
        import yaml
        with yaml_path.open("r") as fh:
            data = yaml.safe_load(fh)
        data["s3_metadata_uri"] = s3_uris["metadata"]
        with yaml_path.open("w") as fh:
            yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print("\n🎉 Done!")


if __name__ == "__main__":
    main()
