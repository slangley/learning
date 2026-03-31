---
name: podcast-to-mp3
description: Convert a podcast script file to an MP3 using text-to-speech and upload it to a Dropbox folder. Arguments: "<path-to-script> [--dropbox-folder <folder>]" (e.g. "podcast-scripts/ai-2024-06-01.md --dropbox-folder /Podcasts")
version: 1.0.0
allowed-tools:
  - Bash
  - Read
  - Write
---

# Podcast Script → MP3 Converter & Dropbox Uploader

Convert a podcast script to an MP3 file with text-to-speech, then upload the result to Dropbox.

## Input parsing

The user's arguments are: **$ARGUMENTS**

Parse as follows:
- **Script path**: the first argument (required) — path to the markdown script file
- **Dropbox folder**: value after `--dropbox-folder` (default: `/Podcasts`)

## Pre-flight checks

Before running the conversion, verify the environment is ready:

1. Check that `skills/requirements.txt` exists. If not, inform the user to run `pip install gtts dropbox` manually.
2. Check that the `DROPBOX_ACCESS_TOKEN` environment variable is set (or a `.env` file exists in `skills/`). If missing, print setup instructions (see below) and stop.
3. Read the script file. If it doesn't exist, stop with a clear error message.

### Setup instructions (if env var is missing)

```
To enable Dropbox uploads you need a Dropbox access token:

1. Go to https://www.dropbox.com/developers/apps and create a new app.
2. Under "Permissions" enable: files.content.write, files.content.read.
3. Generate an access token on the Settings tab.
4. Add it to skills/.env:
     DROPBOX_ACCESS_TOKEN=your_token_here
     DROPBOX_FOLDER=/Podcasts
5. Re-run this skill.
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
