#!/usr/bin/env python3
"""
podcast_to_mp3.py
-----------------
Convert a podcast script (markdown) to an MP3 file using ElevenLabs text-to-speech,
with support for multi-voice ad segments, intro/outro music, and episode metadata.

Usage:
    python podcast_to_mp3.py --script <path> --output <path> [options]

Environment variables (or .env file in the same directory as this script):
    ELEVENLABS_API_KEY     Required when --tts-provider=elevenlabs (the default).
                           Also required for SFX/music when --tts-provider=gemini
                           and the asset is not cached.
    GEMINI_API_KEY         Required when --tts-provider=gemini.
    TTS_PROVIDER           Optional. Default backend if --tts-provider is omitted.
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
from typing import Optional

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
    "george":  "JBFqnCBsd6RMkjVDRZzb",   # George  - Warm, Captivating Storyteller
    "rachel":  "cgSgspJ2msm6clMCkdW9",   # Jessica - Playful, Bright, Warm
    "dave":    "iP95p4xoKVk53GoZ742B",   # Chris   - Charming, Down-to-Earth
    "josh":    "onwK4e9ZLuTAKqWW03F9",   # Daniel  - Steady Broadcaster (replaces retired Josh)
    "adam":    "pNInz6obpgDQGcFmaJgB",   # Adam    - Dominant, Firm
    "sam":     "SAz9YHcvj6GT2YYXdXww",   # River   - Relaxed, Neutral, Informative (replaces retired Sam)
    "sarah":   "EXAVITQu4vr4xnSDxMaL",   # Sarah   - Mature, Reassuring, Confident
    "brian":   "nPczCjzI2devNBz1zQrb",   # Brian   - Deep, Resonant and Comforting
    "lily":    "pFZP5JQG7iQjIQuC4Bku",   # Lily    - Velvety Actress
    "matilda": "XrExE9yKIg1WjnnlVkGX",   # Matilda - Knowledgable, Professional
    "antoni":  "cjVigY5qzO86Huf0OWal",   # Eric    - Smooth, Trustworthy (replaces retired Antoni)
    "arnold":  "IKne3meq5aSn9XLyUdCD",   # Charlie - Deep, Confident, Energetic (replaces retired Arnold)
    "domi":    "Xb7hH8MSUJpSbSDYk0k2",   # Alice   - Clear, Engaging Educator (replaces retired Domi)
}

# Friendly-name → Gemini prebuilt voice. Chosen to roughly match the
# character/tone of each ElevenLabs voice above so --host-voice works
# identically across backends. Raw Gemini voice names (e.g. "Zephyr")
# pass through resolve_voice() unchanged.
GEMINI_VOICES = {
    "george":  "Charon",      # deep / informative
    "rachel":  "Aoede",       # breezy
    "dave":    "Puck",        # upbeat
    "josh":    "Orus",        # firm
    "adam":    "Algieba",     # smooth
    "sam":     "Fenrir",      # excitable
    "sarah":   "Kore",        # firm
    "brian":   "Enceladus",   # breathy
    "lily":    "Leda",        # youthful
    "matilda": "Autonoe",     # bright
    "antoni":  "Iapetus",     # clear
    "arnold":  "Achernar",    # soft
    "domi":    "Despina",     # smooth
}

DEFAULT_VOICE = "george"
DEFAULT_MODEL_ID = "eleven_v3"
DEFAULT_GEMINI_MODEL_ID = "gemini-3.1-flash-tts-preview"

# Gemini TTS input limit. We target 20k tokens (~80k chars) per request to
# leave a safety margin under the 25k cap.
GEMINI_TOKEN_BUDGET = 20_000
GEMINI_CHARS_PER_TOKEN = 4  # rough heuristic when count_tokens is unavailable

# Gemini returns raw 16-bit PCM, mono, 24 kHz.
GEMINI_PCM_SAMPLE_RATE = 24_000
GEMINI_PCM_SAMPLE_WIDTH = 2
GEMINI_PCM_CHANNELS = 1

# Gemini multi-speaker TTS supports at most 2 speakers per request.
GEMINI_MAX_SPEAKERS_PER_REQUEST = 2

SUPPORTED_PROVIDERS = ("elevenlabs", "gemini")

ASSETS_DIR = Path(__file__).parent.parent / "podcast-assets"

SFX_PROMPTS = {
    "intro": ("upbeat podcast intro jingle, energetic and modern", 8.0),
    "outro": ("mellow podcast outro music, smooth fade out", 6.0),
}

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

def preflight_common() -> None:
    """Checks that apply regardless of selected TTS provider."""
    if not shutil.which("ffmpeg"):
        sys.exit(
            "❌  ffmpeg is not installed. pydub requires ffmpeg for audio processing.\n"
            "    Install it with: apt-get install ffmpeg  (or brew install ffmpeg on macOS)"
        )


def preflight_elevenlabs() -> None:
    if not os.environ.get("ELEVENLABS_API_KEY"):
        sys.exit(
            "❌  ELEVENLABS_API_KEY is not set.\n"
            "    Add it to skills/.env or export it as an environment variable.\n"
            "    Get a key at https://elevenlabs.io/app/settings/api-keys"
        )


def preflight_gemini() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit(
            "❌  GEMINI_API_KEY is not set.\n"
            "    Add it to skills/.env or export it as an environment variable.\n"
            "    Get a key at https://aistudio.google.com/app/apikey"
        )


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
    """Resolve a voice name to its ElevenLabs ID, or pass through raw IDs.

    Kept for backwards compatibility with call sites that are ElevenLabs-
    specific (ad-voice resolution inside parse_script, etc.). Prefer
    backend.resolve_voice() for backend-agnostic code paths.
    """
    lower = name_or_id.lower()
    if lower in VOICES:
        return VOICES[lower]
    return name_or_id


def resolve_gemini_voice(name_or_id: str) -> str:
    """Resolve a voice name to its Gemini prebuilt voice name.

    If the caller provided a friendly name (e.g. "george"), map it via
    GEMINI_VOICES. Otherwise pass through unchanged so raw Gemini voice
    names like "Zephyr" still work.
    """
    lower = name_or_id.lower()
    if lower in GEMINI_VOICES:
        return GEMINI_VOICES[lower]
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

            # Headings / markdown separators — flush pending host text and skip.
            # Flushing here keeps each named segment its own TTS call so that
            # per-segment normalization is applied at section granularity rather
            # than across an entire inter-ad block.  Without this, ElevenLabs
            # drifts quieter inside long generations and the single RMS average
            # cannot correct it, producing the progressive level-fade bug.
            if _HEADING.match(line):
                flush_host()
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

# ---------------------------------------------------------------------------
# Audio generation — backend abstraction
# ---------------------------------------------------------------------------


class TTSBackend:
    """Protocol-ish base class for selectable TTS backends."""

    name: str = ""
    default_model: str = ""

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model or self.default_model

    def resolve_voice(self, name_or_id: str) -> str:
        raise NotImplementedError

    def speech(self, text: str, voice: str, output_path: Path) -> None:
        raise NotImplementedError

    def dialogue(self, lines: list[dict], output_path: Path) -> None:
        raise NotImplementedError

    def sound_effect(self, prompt: str, duration: float, output_path: Path) -> None:
        raise NotImplementedError


class ElevenLabsBackend(TTSBackend):
    name = "elevenlabs"
    default_model = DEFAULT_MODEL_ID

    def __init__(self, model: Optional[str] = None) -> None:
        super().__init__(model)
        self._client = None

    def _client_lazy(self):
        if self._client is None:
            try:
                from elevenlabs import ElevenLabs  # type: ignore[import]
            except ImportError:
                sys.exit("❌  elevenlabs is not installed. Run: pip install elevenlabs")
            self._client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
        return self._client

    def resolve_voice(self, name_or_id: str) -> str:
        return resolve_voice_id(name_or_id)

    def speech(self, text: str, voice: str, output_path: Path) -> None:
        client = self._client_lazy()
        audio = client.text_to_speech.convert(
            voice_id=voice,
            text=text,
            model_id=self.model,
            output_format="mp3_44100_128",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as fh:
            for chunk in audio:
                fh.write(chunk)

    def dialogue(self, lines: list[dict], output_path: Path) -> None:
        from elevenlabs.types import DialogueInput
        client = self._client_lazy()
        inputs = [DialogueInput(text=ln["text"], voice_id=ln["voice"]) for ln in lines]
        audio = client.text_to_dialogue.convert(
            inputs=inputs,
            model_id=self.model,
            output_format="mp3_44100_128",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as fh:
            for chunk in audio:
                fh.write(chunk)

    def sound_effect(self, prompt: str, duration: float, output_path: Path) -> None:
        client = self._client_lazy()
        audio = client.text_to_sound_effects.convert(
            text=prompt,
            duration_seconds=duration,
            output_format="mp3_44100_128",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as fh:
            for chunk in audio:
                fh.write(chunk)


class GeminiBackend(TTSBackend):
    """Gemini Flash 3.1 TTS. Respects the 25k-token request limit by chunking."""

    name = "gemini"
    default_model = DEFAULT_GEMINI_MODEL_ID

    def __init__(self, model: Optional[str] = None) -> None:
        super().__init__(model)
        self._client = None
        self._types = None
        self._sfx_fallback: Optional[ElevenLabsBackend] = None

    def _client_lazy(self):
        if self._client is None:
            try:
                from google import genai  # type: ignore[import]
                from google.genai import types as genai_types  # type: ignore[import]
            except ImportError:
                sys.exit("❌  google-genai is not installed. Run: pip install google-genai")
            self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            self._types = genai_types
        return self._client

    def resolve_voice(self, name_or_id: str) -> str:
        return resolve_gemini_voice(name_or_id)

    # -- token counting / chunking ------------------------------------------------

    def _count_tokens(self, text: str) -> int:
        """Use the SDK's count_tokens when available, else fall back to a heuristic."""
        try:
            client = self._client_lazy()
            resp = client.models.count_tokens(model=self.model, contents=text)
            return int(getattr(resp, "total_tokens", 0)) or _heuristic_tokens(text)
        except Exception:
            return _heuristic_tokens(text)

    def _chunk_text(self, text: str) -> list[str]:
        """Split *text* into chunks that fit under GEMINI_TOKEN_BUDGET tokens.

        Uses sentence boundaries first; falls back to word boundaries for
        any single sentence that exceeds the budget on its own. Accounting
        is done in characters (budget * GEMINI_CHARS_PER_TOKEN) to avoid
        per-piece rounding error accumulating across many small pieces.
        """
        if _heuristic_tokens(text) <= GEMINI_TOKEN_BUDGET:
            return [text]

        char_budget = GEMINI_TOKEN_BUDGET * GEMINI_CHARS_PER_TOKEN
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        chunks: list[str] = []
        buf: list[str] = []
        buf_chars = 0
        for sentence in sentences:
            if not sentence:
                continue
            s_chars = len(sentence)
            if s_chars > char_budget:
                if buf:
                    chunks.append(" ".join(buf))
                    buf, buf_chars = [], 0
                chunks.extend(_split_by_words(sentence, GEMINI_TOKEN_BUDGET))
                continue
            extra = s_chars + (1 if buf else 0)
            if buf_chars + extra > char_budget and buf:
                chunks.append(" ".join(buf))
                buf, buf_chars = [sentence], s_chars
            else:
                buf.append(sentence)
                buf_chars += extra
        if buf:
            chunks.append(" ".join(buf))
        return chunks

    # -- PCM → AudioSegment -------------------------------------------------------

    def _pcm_to_segment(self, pcm: bytes):
        from pydub import AudioSegment
        return AudioSegment(
            data=pcm,
            sample_width=GEMINI_PCM_SAMPLE_WIDTH,
            frame_rate=GEMINI_PCM_SAMPLE_RATE,
            channels=GEMINI_PCM_CHANNELS,
        )

    def _generate_pcm_single(self, text: str, voice_name: str) -> bytes:
        client = self._client_lazy()
        types = self._types
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name),
                ),
            ),
        )
        response = client.models.generate_content(
            model=self.model,
            contents=text,
            config=config,
        )
        return _extract_pcm(response)

    def _generate_pcm_multi(self, prompt: str, speaker_voices: list[tuple[str, str]]) -> bytes:
        client = self._client_lazy()
        types = self._types
        speaker_configs = [
            types.SpeakerVoiceConfig(
                speaker=speaker,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice),
                ),
            )
            for speaker, voice in speaker_voices
        ]
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=speaker_configs,
                ),
            ),
        )
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return _extract_pcm(response)

    # -- TTSBackend interface -----------------------------------------------------

    def speech(self, text: str, voice: str, output_path: Path) -> None:
        from pydub import AudioSegment
        chunks = self._chunk_text(text)
        if len(chunks) > 1:
            print(f"    Gemini: splitting into {len(chunks)} chunk(s) (25k-token limit)")
        combined: Optional[AudioSegment] = None
        for idx, chunk in enumerate(chunks):
            pcm = self._generate_pcm_single(chunk, voice)
            seg = self._pcm_to_segment(pcm)
            combined = seg if combined is None else combined + seg
        assert combined is not None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fmt = "wav" if output_path.suffix.lower() == ".wav" else "mp3"
        kwargs: dict = {"format": fmt}
        if fmt == "mp3":
            kwargs["bitrate"] = "128k"
        combined.export(str(output_path), **kwargs)

    def dialogue(self, lines: list[dict], output_path: Path) -> None:
        from pydub import AudioSegment

        unique_voices = []
        for ln in lines:
            if ln["voice"] not in unique_voices:
                unique_voices.append(ln["voice"])

        # Assemble text once so we can test the token budget.
        speaker_map: dict[str, str] = {}
        for idx, voice in enumerate(unique_voices):
            speaker_map[voice] = f"Speaker{idx + 1}"
        dialogue_text = "TTS the following conversation:\n" + "\n".join(
            f"{speaker_map[ln['voice']]}: {ln['text']}" for ln in lines
        )

        use_multi = (
            len(unique_voices) <= GEMINI_MAX_SPEAKERS_PER_REQUEST
            and _heuristic_tokens(dialogue_text) <= GEMINI_TOKEN_BUDGET
        )

        if use_multi:
            speaker_voices = [(speaker_map[v], v) for v in unique_voices]
            pcm = self._generate_pcm_multi(dialogue_text, speaker_voices)
            combined = self._pcm_to_segment(pcm)
        else:
            # Fallback: generate each line as single-speaker and concatenate.
            print(
                f"    Gemini: falling back to per-line synthesis "
                f"({len(unique_voices)} voices, {len(lines)} line(s))"
            )
            combined: Optional[AudioSegment] = None
            for ln in lines:
                chunks = self._chunk_text(ln["text"])
                for chunk in chunks:
                    pcm = self._generate_pcm_single(chunk, ln["voice"])
                    seg = self._pcm_to_segment(pcm)
                    combined = seg if combined is None else combined + seg
            assert combined is not None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fmt = "wav" if output_path.suffix.lower() == ".wav" else "mp3"
        kwargs: dict = {"format": fmt}
        if fmt == "mp3":
            kwargs["bitrate"] = "128k"
        combined.export(str(output_path), **kwargs)

    def sound_effect(self, prompt: str, duration: float, output_path: Path) -> None:
        """Gemini has no SFX endpoint — delegate to ElevenLabs."""
        if self._sfx_fallback is None:
            if not os.environ.get("ELEVENLABS_API_KEY"):
                sys.exit(
                    "❌  Gemini has no sound-effects API, and ELEVENLABS_API_KEY is not set "
                    "for the fallback.\n"
                    "    Either add ELEVENLABS_API_KEY to skills/.env, pre-cache the asset in "
                    "podcast-assets/, or re-run with --no-music."
                )
            self._sfx_fallback = ElevenLabsBackend()
        self._sfx_fallback.sound_effect(prompt, duration, output_path)


# ---------------------------------------------------------------------------
# Chunker helpers (module-level so they're testable independently)
# ---------------------------------------------------------------------------

def _heuristic_tokens(text: str) -> int:
    """Rough char→token estimate used when count_tokens is unavailable."""
    return max(1, len(text) // GEMINI_CHARS_PER_TOKEN)


def _split_by_words(text: str, token_budget: int) -> list[str]:
    """Split *text* on word boundaries so each piece fits under token_budget.

    Tracks character count directly (budget * GEMINI_CHARS_PER_TOKEN) to avoid
    per-word rounding error that would otherwise accumulate across many words.
    """
    char_budget = token_budget * GEMINI_CHARS_PER_TOKEN
    words = text.split()
    chunks: list[str] = []
    buf: list[str] = []
    buf_chars = 0
    for word in words:
        extra = len(word) + (1 if buf else 0)  # space joining, if buf non-empty
        if buf_chars + extra > char_budget and buf:
            chunks.append(" ".join(buf))
            buf, buf_chars = [word], len(word)
        else:
            buf.append(word)
            buf_chars += extra
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def _extract_pcm(response) -> bytes:
    """Pull raw PCM bytes from a Gemini generate_content response."""
    try:
        return response.candidates[0].content.parts[0].inline_data.data
    except (AttributeError, IndexError) as exc:
        sys.exit(f"❌  Gemini response did not contain audio data: {exc}")


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------

def get_backend(provider: str, model: Optional[str] = None) -> TTSBackend:
    provider = provider.lower()
    if provider == "elevenlabs":
        preflight_elevenlabs()
        return ElevenLabsBackend(model=model)
    if provider == "gemini":
        preflight_gemini()
        return GeminiBackend(model=model)
    sys.exit(
        f"❌  Unknown TTS provider: {provider!r}. "
        f"Expected one of: {', '.join(SUPPORTED_PROVIDERS)}."
    )


# ---------------------------------------------------------------------------
# Asset generation (SFX / music)
# ---------------------------------------------------------------------------

def generate_or_load_asset(asset_name: str, backend: TTSBackend) -> Path:
    """Return path to a cached audio asset, generating it via *backend* if missing."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    asset_path = ASSETS_DIR / f"{asset_name}.mp3"
    if asset_path.is_file():
        print(f"  Cached asset: {asset_path}")
        return asset_path

    if asset_name not in SFX_PROMPTS:
        sys.exit(f"❌  Unknown asset: {asset_name}. Expected one of: {list(SFX_PROMPTS.keys())}")

    prompt, duration = SFX_PROMPTS[asset_name]
    print(f"  Generating SFX asset '{asset_name}' ({duration}s)...")
    backend.sound_effect(prompt, duration, asset_path)
    print(f"  Saved asset: {asset_path}")
    return asset_path


# ---------------------------------------------------------------------------
# Audio assembly
# ---------------------------------------------------------------------------

# Target RMS loudness for TTS segments (-14 dBFS matches Spotify/Apple Podcasts spec).
_TARGET_DBFS = -14.0
_PEAK_CEILING_DBFS = -1.0   # headroom guard before RMS gain is applied
_MAX_GAIN_DB = 20.0          # cap amplification so near-silent segments aren't blown up


def _normalize_segment(seg):
    """Normalize an AudioSegment to _TARGET_DBFS RMS with a peak ceiling guard.

    Two-pass approach that fixes the progressive level-fade bug seen with
    ElevenLabs eleven_v3 audio:

    Pass 1 — peak ceiling: if any sample exceeds _PEAK_CEILING_DBFS, reduce gain
    before the RMS step.  eleven_v3 has wide dynamic range; without this the RMS
    normalizer applies large positive gain that causes inter-segment clipping,
    which the subsequent MP3 encoder then compensates by lowering overall level.

    Pass 2 — RMS normalization: bring the segment's average loudness to
    _TARGET_DBFS.  A _MAX_GAIN_DB cap prevents over-amplification of
    near-silent segments (e.g. pauses, tails).
    """
    if seg.dBFS == float("-inf"):
        return seg

    # Pass 1: peak ceiling
    peak = seg.max_dBFS
    if peak > _PEAK_CEILING_DBFS:
        seg = seg.apply_gain(_PEAK_CEILING_DBFS - peak)

    # Pass 2: RMS normalization
    rms = seg.dBFS
    if rms == float("-inf"):
        return seg
    gain = _TARGET_DBFS - rms
    if gain > _MAX_GAIN_DB:
        gain = _MAX_GAIN_DB
    return seg.apply_gain(gain)


def assemble_podcast(segments: list[dict], backend: TTSBackend, tmp_dir: Path) -> bytes:
    """
    Generate audio for each segment and concatenate into a single MP3.

    Returns the final MP3 as bytes.
    """
    from pydub import AudioSegment

    parts: list[AudioSegment] = []
    seg_idx = 0
    # Gemini returns raw PCM; use lossless WAV for intermediate files so we
    # avoid a decode→encode→decode chain that causes progressive level drift.
    use_wav_intermediates = isinstance(backend, GeminiBackend)

    # parse_script already pre-resolves ad/host voices to ElevenLabs IDs via
    # resolve_voice_id. For Gemini we need to re-map those back to friendly
    # names before asking the backend for its native voice. Build a reverse
    # lookup once.
    elevenlabs_id_to_name = {vid: name for name, vid in VOICES.items()}

    def _resolve(raw_voice: str) -> str:
        """Map a stored voice token to the selected backend's voice identifier."""
        if isinstance(backend, ElevenLabsBackend):
            return resolve_voice_id(raw_voice)
        # For non-ElevenLabs backends: if the stored token is an ElevenLabs ID
        # from parse_script, translate back to the friendly name first.
        friendly = elevenlabs_id_to_name.get(raw_voice, raw_voice)
        return backend.resolve_voice(friendly)

    for seg in segments:
        stype = seg["type"]

        if stype == "music":
            asset_path = generate_or_load_asset(seg["asset"], backend)
            parts.append(AudioSegment.from_mp3(str(asset_path)))
            print(f"  [{seg_idx}] Music: {seg['asset']}")

        elif stype == "pause":
            ms = seg.get("duration_ms", 1000)
            parts.append(AudioSegment.silent(duration=ms))
            print(f"  [{seg_idx}] Pause: {ms}ms")

        elif stype == "speech":
            ext = ".wav" if use_wav_intermediates else ".mp3"
            seg_path = tmp_dir / f"seg_{seg_idx:03d}_speech{ext}"
            word_count = len(seg["text"].split())
            print(f"  [{seg_idx}] Speech: {word_count} words (voice: {seg['voice']})")
            backend.speech(seg["text"], _resolve(seg["voice"]), seg_path)
            raw = AudioSegment.from_file(str(seg_path))
            parts.append(_normalize_segment(raw))

        elif stype == "ad":
            ext = ".wav" if use_wav_intermediates else ".mp3"
            seg_path = tmp_dir / f"seg_{seg_idx:03d}_ad{ext}"
            voices_used = set(ln["voice"] for ln in seg["lines"])
            print(f"  [{seg_idx}] Ad: {len(seg['lines'])} lines, {len(voices_used)} voice(s)")
            resolved_lines = [
                {"voice": _resolve(ln["voice"]), "text": ln["text"]}
                for ln in seg["lines"]
            ]
            backend.dialogue(resolved_lines, seg_path)
            raw = AudioSegment.from_file(str(seg_path))
            parts.append(_normalize_segment(raw))

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
    default_provider = os.environ.get("TTS_PROVIDER", "elevenlabs").lower()
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
        "--tts-provider",
        choices=SUPPORTED_PROVIDERS,
        default=default_provider if default_provider in SUPPORTED_PROVIDERS else "elevenlabs",
        dest="tts_provider",
        help=(
            "Which TTS backend to use. Default: elevenlabs (or $TTS_PROVIDER if set). "
            "gemini uses Google's Gemini Flash 3.1 TTS preview."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            f"Model ID (backend-specific). Defaults: {DEFAULT_MODEL_ID} for "
            f"elevenlabs, {DEFAULT_GEMINI_MODEL_ID} for gemini."
        ),
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
    preflight_common()

    script_path = Path(args.script)
    if not script_path.is_file():
        sys.exit(f"❌  Script file not found: {script_path}")

    output_path = Path(args.output)

    # --- Build backend ---
    backend = get_backend(args.tts_provider, model=args.model)

    # --- Resolve host voice ---
    host_voice = args.host_voice.lower()
    host_voice_id = resolve_voice_id(host_voice)  # ElevenLabs ID for parse_script
    print(f"📄 Script:   {script_path}")
    print(f"🧠 Backend:  {backend.name}")
    print(f"🎙️  Host:     {host_voice} ({backend.resolve_voice(host_voice)})")
    print(f"🤖 Model:    {backend.model}")

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
        mp3_bytes = assemble_podcast(segments, backend, tmp_dir)

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
