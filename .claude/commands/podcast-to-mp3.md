---
name: podcast-to-mp3
description: Convert a podcast script file to an MP3 using text-to-speech and upload it to an S3 bucket. Arguments: "<path-to-script> [--s3-bucket <bucket>] [--s3-prefix <prefix>]" (e.g. "podcast-scripts/ai-2024-06-01.md --s3-bucket my-podcasts")
version: 2.0.0
allowed-tools:
  - Bash
  - Read
  - Write
---

# Podcast Script → MP3 Converter & S3 Uploader

Convert a podcast script to an MP3 file with text-to-speech, then upload the result to S3.

## Input parsing

The user's arguments are: **$ARGUMENTS**

Parse as follows:
- **Script path**: the first argument (required) — path to the markdown script file
- **S3 bucket**: value after `--s3-bucket` (default: `$S3_BUCKET` env var)
- **S3 prefix**: value after `--s3-prefix` (default: `podcasts/`)

## Pre-flight checks

Before running the conversion, verify the environment is ready:

1. Check that `skills/requirements.txt` exists. If not, inform the user to run `pip install elevenlabs boto3` manually.
2. Check that the `ELEVENLABS_API_KEY` environment variable is set (or a `.env` file exists in `skills/`). If missing, print setup instructions (see below) and stop.
3. Check that either `S3_BUCKET` is set or `--s3-bucket` is passed. If missing, print S3 setup instructions and stop.
4. Read the script file. If it doesn't exist, stop with a clear error message.

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
     S3_PREFIX=podcasts/
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

## Step 2 — Prepare the script text

Read the script markdown file and strip production cues so only spoken text remains:

- Remove all lines that match `[MUSIC - *]`, `[PAUSE]`, `[AD BREAK]`, `## SEGMENT`, `---`, and any other markdown headings/cues.
- Keep only lines that start with `[HOST]`, removing the `[HOST]` label itself.
- Join all lines with a single space.

This cleaned text is what will be passed to text-to-speech.

## Step 3 — Convert to MP3

Run the Python helper script:

```bash
python skills/podcast_to_mp3.py \
  --script "<script-path>" \
  --output "<output-mp3-path>" \
  --dropbox-folder "<dropbox-folder>"
```

Where `<output-mp3-path>` mirrors the script path but with a `.mp3` extension inside a `podcast-mp3s/` directory (create it if needed).

For example: `podcast-scripts/ai-2024-06-01.md` → `podcast-mp3s/ai-2024-06-01.mp3`

## Step 4 — Report results

After the script exits successfully, report:

```
✅ MP3 generated: podcast-mp3s/<filename>.mp3
✅ Uploaded to Dropbox: <dropbox-folder>/<filename>.mp3
```

If there are errors (network failure, bad token, etc.), display the Python traceback and suggest fixes.
