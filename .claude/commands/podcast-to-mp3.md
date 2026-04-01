---
name: podcast-to-mp3
description: Convert a podcast script to MP3 with multi-voice ads, intro/outro music, and episode metadata. Arguments: "<path-to-script> [--host-voice <name>] [--model <id>] [--no-music] [--s3-bucket <bucket>]"
version: 3.0.0
allowed-tools:
  - Bash
  - Read
  - Write
---

# Podcast Script → MP3 Converter & S3 Uploader

Convert a podcast script to an MP3 file with multi-voice support, intro/outro music, and episode metadata YAML.

## Input parsing

The user's arguments are: **$ARGUMENTS**

Parse as follows:
- **Script path**: the first argument (required) — path to the markdown script file
- **Host voice**: value after `--host-voice` or `--voice` (default: `george`). Available voices: george, rachel, dave, josh, adam, sam, sarah, brian, lily, matilda, antoni, arnold, domi. Can also be a raw ElevenLabs voice ID.
- **Model**: value after `--model` (default: `eleven_v3`)
- **No music**: if `--no-music` is present, skip intro/outro jingles
- **S3 bucket**: value after `--s3-bucket` (default: `$S3_BUCKET` env var)
- **S3 prefix**: value after `--s3-prefix` (default: `episodes/`)

## Pre-flight checks

Before running the conversion, verify the environment is ready:

1. Check that `skills/requirements.txt` exists. If not, inform the user to run `pip install elevenlabs boto3 pydub pyyaml` manually.
2. Check that the `ELEVENLABS_API_KEY` environment variable is set (or a `.env` file exists in `skills/`). If missing, print setup instructions (see below) and stop.
3. Check that either `S3_BUCKET` is set or `--s3-bucket` is passed. If missing, print S3 setup instructions and stop.
4. Check that `ffmpeg` is installed (required by pydub). If missing, print install instructions and stop.
5. Read the script file. If it doesn't exist, stop with a clear error message.

### Setup instructions (if ElevenLabs key is missing)

```
To enable text-to-speech you need an ElevenLabs API key:

1. Go to https://elevenlabs.io/app/settings/api-keys and create an API key.
2. Add it to skills/.env:
     ELEVENLABS_API_KEY=your_key_here
3. Re-run this skill.
```

### Setup instructions (if S3 bucket is missing)

```
To enable S3 uploads you need an S3 bucket and AWS credentials:

1. Add your bucket name to skills/.env:
     S3_BUCKET=your-bucket-name
     S3_PREFIX=episodes/
2. Add AWS credentials (or use ~/.aws/credentials / IAM role):
     AWS_ACCESS_KEY_ID=your_key_id
     AWS_SECRET_ACCESS_KEY=your_secret
     AWS_REGION=us-east-1
3. Ensure the IAM user/role has s3:PutObject on the bucket.
4. Re-run this skill.
```

## Step 1 — Install dependencies (if needed)

Run the following to ensure Python dependencies are available:

```bash
pip install -q -r skills/requirements.txt
```

If the install fails, print the error and stop.

## Step 2 — Convert to MP3

Run the Python helper script:

```bash
python skills/podcast_to_mp3.py \
  --script "<script-path>" \
  --output "<output-mp3-path>" \
  --host-voice "<voice>" \
  --model "<model>"
```

Add `--no-music` if the user passed it.

Where `<output-mp3-path>` mirrors the script path but with a `.mp3` extension inside a `podcast-mp3s/` directory (create it if needed).

For example: `podcast-scripts/ai-2024-06-01.md` → `podcast-mp3s/ai-2024-06-01.mp3`

## Script format reference

The script supports these markers (handled automatically by the Python script):

| Marker | Behavior |
|--------|----------|
| `[MUSIC - INTRO]` | Inserts cached intro jingle (generated via ElevenLabs SFX on first run) |
| `[MUSIC - OUTRO]` | Inserts cached outro jingle |
| `[PAUSE]` | Inserts 1 second of silence |
| `[HOST] text` | Host speech — single-voice TTS using `--host-voice` |
| `[AD BREAK]` | Starts an ad segment; `[ding]` audio tag auto-prepended |
| `[VOICE:name] text` | Ad/guest line — uses named voice via Text to Dialogue API |
| `[AD END]` | Ends ad segment; `[ding]` audio tag auto-appended |
| `(Source: name, date)` | Stripped from audio; collected into episode YAML metadata |
| `[laughs]`, `[sighs]`, etc. | ElevenLabs v3 audio tags — rendered as sounds/emotions |

## Step 3 — Report results

After the script exits successfully, report:

```
✅ MP3 generated: podcast-mp3s/<filename>.mp3
✅ Episode metadata: podcast-episodes/<filename>.yaml
✅ Uploaded to S3: episodes/<filename>.mp3, scripts/<filename>.md, metadata/<filename>.yaml
```

If there are errors (network failure, bad token, etc.), display the Python traceback and suggest fixes.
