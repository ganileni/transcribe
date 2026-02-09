# Transcribe

A standalone application for recording, transcribing, and summarizing meetings.

## Features

- **Audio Recording**: Record from microphone and system audio
- **Transcription**: Automatic transcription via AssemblyAI with speaker diarization
- **Speaker Labeling**: GUI for assigning real names to detected speakers
- **Summarization**: Generate meeting summaries using Claude Code
- **File Watching**: Automatic processing of new recordings
- **Obsidian Integration**: Output format compatible with Obsidian vault

## Installation

### Dependencies

Install required packages:

```bash
sudo apt install ffmpeg jq curl sqlite3 zenity inotify-tools pulseaudio-utils
```

For summarization, install [Claude Code](https://claude.ai/claude-code):

```bash
npm install -g @anthropic-ai/claude-code
```

### Install Transcribe

```bash
./install.sh
```

The installer will:
1. Check dependencies
2. Create configuration at `~/.config/transcribe/`
3. Initialize the SQLite database
4. Create a symlink in `~/.local/bin/`
5. Optionally create a desktop launcher
6. Optionally set up the systemd watcher service

### API Key

Create `~/.transcribe.apikey.json` with your AssemblyAI API key:

```json
{
  "assemblyai_api_key": "your-key-here"
}
```

Get an API key at [assemblyai.com](https://www.assemblyai.com/).

## Configuration

Edit `~/.config/transcribe/config.json`:

```json
{
  "watch_dir": "~/recordings",
  "raw_transcripts_dir": "~/transcripts/raw",
  "summaries_dir": "~/transcripts/summaries",
  "done_dir": "~/recordings/.done",
  "api_key_file": "~/.transcribe.apikey.json",
  "auto_process": true
}
```

| Option | Description |
|--------|-------------|
| `watch_dir` | Directory to watch for new audio files |
| `raw_transcripts_dir` | Where to save raw transcripts (YAML) |
| `summaries_dir` | Where to save meeting summaries (Markdown) |
| `done_dir` | Where to move processed audio files |
| `api_key_file` | Path to AssemblyAI API key JSON |
| `auto_process` | Auto-transcribe when watcher detects new files |

## Usage

### GUI Mode

```bash
transcribe gui
```

The GUI provides:
- Recording controls (start/stop)
- List of audio files with transcription status
- Speaker labeling interface
- Batch processing

### Command Line

```bash
# Show status
transcribe status

# Transcribe a single file
transcribe transcribe ~/recording.mp4

# Process all pending files
transcribe process

# Label speakers in a transcript
transcribe label ~/transcript.yaml

# Generate summary (requires labeled transcript)
transcribe summarise ~/transcript.yaml "Team Standup"

# Start/stop recording
transcribe record start
transcribe record stop

# Watch for new files
transcribe watch

# Edit configuration
transcribe config
```

### Systemd Service

Enable automatic watching:

```bash
systemctl --user enable transcribe-watcher
systemctl --user start transcribe-watcher
```

Check status:

```bash
systemctl --user status transcribe-watcher
journalctl --user -u transcribe-watcher -f
```

## Workflow

1. **Record** a meeting (via GUI, CLI, or external mobile recorder app)
2. **Transcribe** the audio (automatic if watcher is running, or manually)
3. **Label** speakers - the GUI shows sample utterances to help identify each speaker
4. **Summarize** - generates a markdown summary with action items

## Output Formats

### Raw Transcript (YAML)

```yaml
---
source_file: meeting-2024-01-15.mp4
transcribed: 2024-01-15T14:30:00
duration_seconds: 3600
labeled: true
speakers:
  - id: "Speaker A"
    name: "Alice"
  - id: "Speaker B"
    name: "Bob"
---
utterances:
  - speaker: "Alice"
    start: 0.0
    end: 5.2
    text: "Hello everyone, let's get started."
  - speaker: "Bob"
    start: 5.5
    end: 12.1
    text: "Thanks for joining..."
```

### Summary (Markdown)

```markdown
---
date: 2024-01-15
title: Team Standup
participants: [Alice, Bob]
---

> Raw transcript: [[raw-transcription/2024-01-15-14-30-transcript]]

## Summary
...

## Key Points
...

## Action Items
- [ ] **Alice**: Review the PR by Friday
- [ ] **Bob**: Update documentation
```

## Troubleshooting

### Recording doesn't capture system audio

Install PulseAudio utilities:

```bash
sudo apt install pulseaudio-utils
```

Make sure a monitor source exists:

```bash
pactl list short sources | grep monitor
```

### Transcription fails

1. Check your API key is valid
2. Verify the audio file is accessible
3. Check network connectivity
4. View detailed output: `transcribe transcribe file.mp4 2>&1`

### Watcher not detecting files

1. Check inotify-tools is installed
2. Verify the watch directory exists
3. Check systemd service logs: `journalctl --user -u transcribe-watcher`

### GUI doesn't launch

Install zenity or yad:

```bash
sudo apt install zenity
# or
sudo apt install yad
```

## Uninstallation

```bash
./uninstall.sh
```

This removes:
- Symlink from `~/.local/bin/`
- Desktop launcher
- Systemd service

Optionally removes `~/.config/transcribe/` (config and database).

## File Locations

| Location | Purpose |
|----------|---------|
| `~/.config/transcribe/config.json` | User configuration |
| `~/.config/transcribe/transcribe.db` | SQLite database |
| `~/.local/bin/transcribe` | Symlink to executable |
| `~/.local/share/applications/transcribe.desktop` | Desktop launcher |
| `~/.config/systemd/user/transcribe-watcher.service` | Systemd service |

## License

MIT
