# Podcast Skills

Two Claude Code slash commands that let you research a topic, write a podcast
script, and convert it to an MP3 that gets automatically uploaded to Dropbox.

---

## Skills overview

| Command | What it does |
|---------|-------------|
| `/podcast-script` | Research a topic and write a 10–15 min podcast script |
| `/podcast-to-mp3` | Convert a script to MP3 and upload it to Dropbox |

---

## Quick start

### 1. Install Python dependencies

```bash
pip install -r skills/requirements.txt
```

### 2. Set up Dropbox credentials

1. Go to <https://www.dropbox.com/developers/apps> and create a **Scoped access** app.
2. Under **Permissions**, enable:
   - `files.content.write`
   - `files.content.read`
3. On the **Settings** tab, click **Generate** under *OAuth 2 → Generated access token*.
4. Copy `skills/.env.example` to `skills/.env`:
   ```bash
   cp skills/.env.example skills/.env
   ```
5. Open `skills/.env` and paste your token:
   ```
   DROPBOX_ACCESS_TOKEN=sl.xxxxxxxxxxxxxxxx...
   DROPBOX_FOLDER=/Podcasts
   ```

> **Security note:** `skills/.env` is listed in `.gitignore` and will never be committed.

---

## Usage

### `/podcast-script` — Research & write a script

```
/podcast-script <topic> [--window <duration>]
```

**Examples:**

```
/podcast-script Rust programming language
/podcast-script AI agents --window 2 weeks
/podcast-script TypeScript 5 --window 3 days
```

**What happens:**

1. Claude searches the web for recent news, releases, tutorials, tidbits, and
   community commentary about the topic within the given time window.
2. A structured 10–15 minute podcast script is written and saved to:
   ```
   podcast-scripts/<topic-slug>-<YYYY-MM-DD>.md
   ```

**Output format** (the script file):

```markdown
## SEGMENT 1 — Top News & Releases

[HOST] Welcome back to the show! This week in Rust...

[PAUSE]

[HOST] First up, Rust 1.79 was released on June 13th...
```

---

### `/podcast-to-mp3` — Convert script to MP3 & upload

```
/podcast-to-mp3 <path-to-script> [--dropbox-folder <folder>]
```

**Examples:**

```
/podcast-to-mp3 podcast-scripts/rust-programming-language-2024-06-15.md
/podcast-to-mp3 podcast-scripts/ai-agents-2024-06-15.md --dropbox-folder /MyPodcasts
```

**What happens:**

1. The skill reads the script and strips out production cues (`[MUSIC]`, `[PAUSE]`, etc.).
2. The spoken text is converted to speech using Google Text-to-Speech (gTTS).
3. The resulting MP3 is saved to `podcast-mp3s/<filename>.mp3`.
4. The MP3 is uploaded to your configured Dropbox folder.

---

## Python helper script

The `skills/podcast_to_mp3.py` script can also be run directly from the command line:

```bash
# Convert and upload
python skills/podcast_to_mp3.py \
  --script podcast-scripts/rust-2024-06-15.md \
  --output podcast-mp3s/rust-2024-06-15.mp3 \
  --dropbox-folder /Podcasts

# Convert only (skip Dropbox upload)
python skills/podcast_to_mp3.py \
  --script podcast-scripts/rust-2024-06-15.md \
  --output podcast-mp3s/rust-2024-06-15.mp3 \
  --no-upload
```

**CLI flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--script` | *(required)* | Path to podcast script markdown file |
| `--output` | *(required)* | Output path for the MP3 |
| `--dropbox-folder` | `/Podcasts` | Dropbox destination folder |
| `--lang` | `en` | BCP 47 language code for TTS |
| `--no-upload` | `false` | Skip Dropbox upload (local test mode) |

---

## Directory layout

```
.claude/
  commands/
    podcast-script.md      ← /podcast-script slash command
    podcast-to-mp3.md      ← /podcast-to-mp3 slash command

skills/
  podcast_to_mp3.py        ← Python TTS + Dropbox helper
  requirements.txt         ← Python dependencies
  .env.example             ← Template for credentials
  .env                     ← Your credentials (NOT committed)
  README.md                ← This file

podcast-scripts/           ← Generated script files (auto-created)
podcast-mp3s/              ← Generated MP3 files (auto-created)
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `gTTS is not installed` | Run `pip install -r skills/requirements.txt` |
| `DROPBOX_ACCESS_TOKEN is not set` | Create `skills/.env` from `.env.example` |
| `Invalid Dropbox access token` | Regenerate the token in the Dropbox developer portal |
| `Dropbox upload failed: ApiError` | Check folder permissions and token scopes |
| Script has no spoken text | Ensure the script contains `[HOST] ...` lines |
