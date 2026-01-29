# Meeting Transcription Workflow

A complete system for recording, transcribing, and summarising meetings across Android and Linux.

## Architecture Overview

```
┌─────────────────────┐     ┌─────────────────────┐
│  Android Phone      │     │  Linux Desktop      │
│  Mobile Recorder│     │  meeting-recorder.sh│
└─────────┬───────────┘     └─────────┬───────────┘
          │                           │
          ▼                           ▼
┌─────────────────────────────────────────────────┐
│              ~/recordings       │
│              (synced via Google Drive)          │
└─────────────────────────┬───────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────┐
│                    Scriberr                     │
│         (Folder Watcher + Groq API)             │
│    • Transcribes with diarisation               │
│    • Moves processed files to .done/            │
└─────────────────────────┬───────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────┐
│              ~/transcripts/                     │
│    • Raw transcripts (.md)                      │
│    • Summaries (.summary.md)                    │
└─────────────────────────┬───────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────┐
│            Speaker Labelling Script             │
│    • Shows speaker samples                      │
│    • Prompts for names                          │
│    • Find/replace in transcript + summary       │
└─────────────────────────────────────────────────┘
```

---

## 1. Android Recording (Mobile Recorder)

**Status:** Already configured

**Setup:**
- App: Mobile Recorder (Play Store)
- Output format: MP3 or WAV (MP3 recommended for size)
- Sync folder: `~/recordings`
- Google Drive sync: Enabled

**No action required.** Files automatically appear in the sync folder when your phone connects to wifi.

---

## 2. Scriberr + Groq API

### 2.1 Installation

```bash
# Install via Homebrew (recommended for simplicity)
brew tap rishikanthc/scriberr
brew install scriberr

# Or via Docker
docker run -d \
  --name scriberr \
  -p 8080:8080 \
  -v scriberr_data:/app/data \
  -e GROQ_API_KEY=your_key_here \
  --restart unless-stopped \
  ghcr.io/rishikanthc/scriberr:latest
```

### 2.2 Configuration

Create `~/.config/scriberr/config.yaml`:

```yaml
# Scriberr Configuration

# Groq API for fast, cheap transcription
transcription:
  provider: groq
  api_key: ${GROQ_API_KEY}  # Set via environment variable
  model: whisper-large-v3-turbo

# Diarisation (speaker detection)
diarisation:
  enabled: true
  huggingface_token: ${HF_TOKEN}  # Required for pyannote models

# Folder watcher
watcher:
  enabled: true
  input_dir: ~/recordings
  output_dir: ~/transcripts
  poll_interval: 60  # seconds

# Output format
output:
  format: markdown
  include_timestamps: true
  include_speaker_labels: true
```

### 2.3 Marking Files as Transcribed

Scriberr does not natively mark files as processed. Wrap it with a script that moves completed files:

**File: `~/bin/scriberr-watcher.sh`**

```bash
#!/bin/bash
# Wrapper for Scriberr that marks files as processed

INPUT_DIR="$HOME/recordings"
OUTPUT_DIR="$HOME/transcripts"
DONE_DIR="$INPUT_DIR/.done"
LOG_FILE="$HOME/.local/log/scriberr.log"

mkdir -p "$DONE_DIR" "$OUTPUT_DIR" "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

process_file() {
    local file="$1"
    local basename=$(basename "$file")
    local name="${basename%.*}"
    
    log "Processing: $basename"
    
    # Call Scriberr API (adjust endpoint as needed)
    curl -s -X POST "http://localhost:8080/api/transcribe" \
        -F "file=@$file" \
        -F "diarisation=true" \
        -o "$OUTPUT_DIR/${name}.md"
    
    if [[ $? -eq 0 && -s "$OUTPUT_DIR/${name}.md" ]]; then
        mv "$file" "$DONE_DIR/"
        log "Completed: $basename -> ${name}.md"
        
        # Trigger summarisation
        "$HOME/bin/summarise-transcript.sh" "$OUTPUT_DIR/${name}.md"
    else
        log "ERROR: Failed to transcribe $basename"
    fi
}

# Watch for new files
inotifywait -m -e close_write -e moved_to "$INPUT_DIR" --format '%f' 2>/dev/null | while read filename; do
    # Skip hidden files and non-audio
    [[ "$filename" == .* ]] && continue
    [[ "$filename" =~ \.(mp3|wav|m4a|ogg|flac)$ ]] || continue
    
    # Wait for sync to complete (file might still be writing)
    sleep 5
    
    process_file "$INPUT_DIR/$filename"
done
```

**Alternative: Simple cron-based approach**

```bash
# Add to crontab: crontab -e
*/5 * * * * $HOME/bin/process-recordings.sh
```

**File: `~/bin/process-recordings.sh`**

```bash
#!/bin/bash
INPUT_DIR="$HOME/recordings"
OUTPUT_DIR="$HOME/transcripts"
DONE_DIR="$INPUT_DIR/.done"

mkdir -p "$DONE_DIR" "$OUTPUT_DIR"

for file in "$INPUT_DIR"/*.{mp3,wav,m4a,ogg,flac} 2>/dev/null; do
    [[ -f "$file" ]] || continue
    
    basename=$(basename "$file")
    name="${basename%.*}"
    
    # Skip if already transcribed
    [[ -f "$OUTPUT_DIR/${name}.md" ]] && continue
    [[ -f "$DONE_DIR/$basename" ]] && continue
    
    # Transcribe via Scriberr API
    response=$(curl -s -X POST "http://localhost:8080/api/transcribe" \
        -F "file=@$file" \
        -F "diarisation=true")
    
    if [[ -n "$response" ]]; then
        echo "$response" > "$OUTPUT_DIR/${name}.md"
        mv "$file" "$DONE_DIR/"
        
        # Trigger summarisation
        "$HOME/bin/summarise-transcript.sh" "$OUTPUT_DIR/${name}.md"
    fi
done
```

---

## 3. Summarisation Script

**File: `~/bin/summarise-transcript.sh`**

```bash
#!/bin/bash
# Summarise a transcript using Claude or other LLM

set -e

TRANSCRIPT="$1"
MODEL="${SUMMARY_MODEL:-claude-sonnet-4-20250514}"
API_KEY="${ANTHROPIC_API_KEY}"

if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
    echo "Usage: summarise-transcript.sh <transcript.md>"
    exit 1
fi

OUTPUT="${TRANSCRIPT%.md}.summary.md"

# Default prompt (override with SUMMARY_PROMPT env var)
DEFAULT_PROMPT='You are summarising a meeting transcript.

Create a structured summary with:
1. **Meeting Overview** - One paragraph capturing the main purpose and outcome
2. **Key Decisions** - Bullet list of decisions made
3. **Action Items** - Who committed to do what, with deadlines if mentioned
4. **Open Questions** - Unresolved issues requiring follow-up
5. **Notable Quotes** - 2-3 significant statements worth preserving (with speaker attribution)

Be concise. Use the speaker labels from the transcript. If speakers are labelled generically (Speaker 0, Speaker 1), preserve those labels.

Transcript follows:
'

PROMPT="${SUMMARY_PROMPT:-$DEFAULT_PROMPT}"

# Read transcript
CONTENT=$(cat "$TRANSCRIPT")

# Call Claude API
RESPONSE=$(curl -s "https://api.anthropic.com/v1/messages" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -d "$(jq -n \
        --arg model "$MODEL" \
        --arg prompt "$PROMPT" \
        --arg content "$CONTENT" \
        '{
            model: $model,
            max_tokens: 4096,
            messages: [{
                role: "user",
                content: ($prompt + "\n\n" + $content)
            }]
        }')")

# Extract text from response
SUMMARY=$(echo "$RESPONSE" | jq -r '.content[0].text // empty')

if [[ -z "$SUMMARY" ]]; then
    echo "ERROR: Failed to generate summary"
    echo "$RESPONSE" | jq .
    exit 1
fi

# Write summary with metadata header
{
    echo "---"
    echo "source: $(basename "$TRANSCRIPT")"
    echo "generated: $(date -Iseconds)"
    echo "model: $MODEL"
    echo "---"
    echo ""
    echo "$SUMMARY"
} > "$OUTPUT"

echo "Summary written to: $OUTPUT"
```

### Configuration

Set environment variables in `~/.bashrc` or `~/.profile`:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export SUMMARY_MODEL="claude-sonnet-4-20250514"  # or claude-haiku-4-5-20251001 for cheaper/faster

# Optional: Custom prompt
export SUMMARY_PROMPT="Your custom prompt here..."
```

### Alternative: Using Ollama (local)

```bash
#!/bin/bash
# Local summarisation with Ollama

TRANSCRIPT="$1"
MODEL="${OLLAMA_MODEL:-llama3.1:8b}"
OUTPUT="${TRANSCRIPT%.md}.summary.md"

PROMPT="Summarise this meeting transcript. Include: key decisions, action items, and open questions.

$(cat "$TRANSCRIPT")"

ollama run "$MODEL" "$PROMPT" > "$OUTPUT"
```

---

## 4. Linux Recording Script

**File: `~/bin/meeting-recorder.sh`**

```bash
#!/bin/bash
# Meeting recorder with GUI - records mic + system audio to mono MP3

OUTPUT_DIR="$HOME/recordings"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
FILENAME="meeting-$TIMESTAMP.mp3"
FILEPATH="$OUTPUT_DIR/$FILENAME"
PIDFILE="/tmp/meeting-recorder.pid"
PAUSEFILE="/tmp/meeting-recorder.paused"

mkdir -p "$OUTPUT_DIR"

# Cleanup function
cleanup() {
    rm -f "$PIDFILE" "$PAUSEFILE"
    # Kill any background processes
    jobs -p | xargs -r kill 2>/dev/null
}
trap cleanup EXIT

# Check dependencies
for cmd in ffmpeg yad pactl; do
    if ! command -v "$cmd" &>/dev/null; then
        yad --error --text="Missing dependency: $cmd"
        exit 1
    fi
done

# Get default devices
MIC_SOURCE="default"
MONITOR_SOURCE="$(pactl get-default-sink).monitor"

# Verify monitor source exists
if ! pactl list sources short | grep -q "$MONITOR_SOURCE"; then
    # Fallback: find any monitor source
    MONITOR_SOURCE=$(pactl list sources short | grep '\.monitor' | head -1 | cut -f2)
fi

if [[ -z "$MONITOR_SOURCE" ]]; then
    yad --error --text="Cannot find system audio monitor source"
    exit 1
fi

# Start recording in background
start_recording() {
    ffmpeg -y \
        -f pulse -i "$MIC_SOURCE" \
        -f pulse -i "$MONITOR_SOURCE" \
        -filter_complex "amix=inputs=2:duration=longest,pan=mono|c0=0.5*c0+0.5*c1" \
        -codec:a libmp3lame -q:a 2 \
        "$FILEPATH" &>/dev/null &
    
    echo $! > "$PIDFILE"
}

# Pause recording (SIGSTOP)
pause_recording() {
    if [[ -f "$PIDFILE" ]]; then
        kill -STOP $(cat "$PIDFILE") 2>/dev/null
        touch "$PAUSEFILE"
    fi
}

# Resume recording (SIGCONT)
resume_recording() {
    if [[ -f "$PIDFILE" ]]; then
        kill -CONT $(cat "$PIDFILE") 2>/dev/null
        rm -f "$PAUSEFILE"
    fi
}

# Stop recording
stop_recording() {
    if [[ -f "$PIDFILE" ]]; then
        kill -INT $(cat "$PIDFILE") 2>/dev/null
        wait $(cat "$PIDFILE") 2>/dev/null
        rm -f "$PIDFILE" "$PAUSEFILE"
    fi
}

# Check if paused
is_paused() {
    [[ -f "$PAUSEFILE" ]]
}

# GUI with yad
show_gui() {
    # Start recording immediately
    start_recording
    
    # Show control window
    while true; do
        if is_paused; then
            ACTION=$(yad --title="Meeting Recorder (PAUSED)" \
                --width=300 --height=150 \
                --text="Recording: $FILENAME\n\n<b>PAUSED</b>" \
                --button="Resume:2" \
                --button="Stop:0" \
                --center)
            RESULT=$?
        else
            ACTION=$(yad --title="Meeting Recorder" \
                --width=300 --height=150 \
                --text="Recording: $FILENAME\n\n🔴 Recording..." \
                --button="Pause:1" \
                --button="Stop:0" \
                --center)
            RESULT=$?
        fi
        
        case $RESULT in
            0)  # Stop
                stop_recording
                yad --info --text="Recording saved to:\n$FILEPATH" --width=400
                break
                ;;
            1)  # Pause
                pause_recording
                ;;
            2)  # Resume
                resume_recording
                ;;
            252) # Window closed
                stop_recording
                break
                ;;
        esac
    done
}

# Alternative: Minimal zenity version (no pause)
show_gui_minimal() {
    start_recording
    
    zenity --info \
        --title="Meeting Recorder" \
        --text="Recording to: $FILENAME\n\nClick OK to stop." \
        --ok-label="Stop Recording"
    
    stop_recording
    zenity --info --text="Saved: $FILEPATH"
}

# Run
if command -v yad &>/dev/null; then
    show_gui
else
    show_gui_minimal
fi
```

### Installation

```bash
# Install dependencies
sudo apt install yad ffmpeg pulseaudio-utils

# Make executable
chmod +x ~/bin/meeting-recorder.sh

# Create desktop launcher (optional)
cat > ~/.local/share/applications/meeting-recorder.desktop << 'EOF'
[Desktop Entry]
Name=Meeting Recorder
Comment=Record meetings with mic and system audio
Exec=/home/$USER/bin/meeting-recorder.sh
Icon=audio-input-microphone
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Recorder;
EOF
```

### Usage

- Click the desktop icon or run `meeting-recorder.sh`
- Red window appears showing recording status
- Click "Pause" to pause (SIGSTOP to ffmpeg)
- Click "Resume" to continue
- Click "Stop" to finish and save

The recording saves to the same folder as Mobile Recorder, so it gets picked up by the transcription pipeline automatically.

---

## 5. Speaker Labelling Script

**File: `~/bin/label-speakers.sh`**

```bash
#!/bin/bash
# Interactive speaker labelling for transcripts

set -e

TRANSCRIPT="$1"

if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
    echo "Usage: label-speakers.sh <transcript.md>"
    exit 1
fi

SUMMARY="${TRANSCRIPT%.md}.summary.md"
BACKUP="${TRANSCRIPT}.bak"

# Backup original
cp "$TRANSCRIPT" "$BACKUP"

# Extract unique speaker labels (e.g., "Speaker 0", "Speaker 1", "SPEAKER_00")
SPEAKERS=$(grep -oE '(Speaker [0-9]+|SPEAKER_[0-9]+)' "$TRANSCRIPT" | sort -u)

if [[ -z "$SPEAKERS" ]]; then
    echo "No speaker labels found in transcript."
    exit 0
fi

echo "Found speakers:"
echo "$SPEAKERS"
echo ""

declare -A SPEAKER_MAP

for speaker in $SPEAKERS; do
    echo "========================================"
    echo "Speaker: $speaker"
    echo "========================================"
    echo ""
    echo "Sample utterances:"
    echo "----------------------------------------"
    
    # Show first 3 utterances from this speaker
    grep -A1 "^$speaker:" "$TRANSCRIPT" 2>/dev/null | head -20 || \
    grep -B1 -A1 "$speaker" "$TRANSCRIPT" | head -20
    
    echo ""
    echo "----------------------------------------"
    read -p "Enter name for '$speaker' (or press Enter to skip): " name
    
    if [[ -n "$name" ]]; then
        SPEAKER_MAP["$speaker"]="$name"
        echo "  -> $speaker will become: $name"
    else
        echo "  -> Skipping $speaker"
    fi
    echo ""
done

# Confirm changes
echo ""
echo "========================================"
echo "Summary of changes:"
echo "========================================"
for speaker in "${!SPEAKER_MAP[@]}"; do
    echo "  $speaker -> ${SPEAKER_MAP[$speaker]}"
done
echo ""
read -p "Apply these changes? [y/N] " confirm

if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted. Original file unchanged."
    rm -f "$BACKUP"
    exit 0
fi

# Apply replacements
for speaker in "${!SPEAKER_MAP[@]}"; do
    name="${SPEAKER_MAP[$speaker]}"
    
    # Escape special characters for sed
    speaker_escaped=$(printf '%s\n' "$speaker" | sed 's/[[\.*^$()+?{|]/\\&/g')
    name_escaped=$(printf '%s\n' "$name" | sed 's/[&/\]/\\&/g')
    
    # Replace in transcript
    sed -i "s/$speaker_escaped/$name_escaped/g" "$TRANSCRIPT"
    
    # Replace in summary if it exists
    if [[ -f "$SUMMARY" ]]; then
        sed -i "s/$speaker_escaped/$name_escaped/g" "$SUMMARY"
    fi
done

echo ""
echo "Done! Changes applied to:"
echo "  - $TRANSCRIPT"
[[ -f "$SUMMARY" ]] && echo "  - $SUMMARY"
echo ""
echo "Backup saved to: $BACKUP"
```

### Enhanced Version with Fuzzy Matching

**File: `~/bin/label-speakers-smart.sh`**

```bash
#!/bin/bash
# Smart speaker labelling with pattern detection

set -e

TRANSCRIPT="$1"

if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
    echo "Usage: label-speakers-smart.sh <transcript.md>"
    exit 1
fi

SUMMARY="${TRANSCRIPT%.md}.summary.md"

# Detect speaker label format
detect_format() {
    if grep -qE '^Speaker [0-9]+:' "$TRANSCRIPT"; then
        echo "colon"  # "Speaker 0: text"
    elif grep -qE '^\[Speaker [0-9]+\]' "$TRANSCRIPT"; then
        echo "bracket"  # "[Speaker 0] text"
    elif grep -qE '^SPEAKER_[0-9]+:' "$TRANSCRIPT"; then
        echo "underscore"  # "SPEAKER_00: text"
    elif grep -qE '\*\*Speaker [0-9]+\*\*' "$TRANSCRIPT"; then
        echo "bold"  # "**Speaker 0**"
    else
        echo "unknown"
    fi
}

FORMAT=$(detect_format)
echo "Detected format: $FORMAT"

# Extract speakers based on format
case "$FORMAT" in
    colon)
        PATTERN='^(Speaker [0-9]+):'
        ;;
    bracket)
        PATTERN='^\[(Speaker [0-9]+)\]'
        ;;
    underscore)
        PATTERN='^(SPEAKER_[0-9]+):'
        ;;
    bold)
        PATTERN='\*\*(Speaker [0-9]+)\*\*'
        ;;
    *)
        # Fallback: any "Speaker N" pattern
        PATTERN='(Speaker [0-9]+|SPEAKER_[0-9]+)'
        ;;
esac

SPEAKERS=$(grep -oE "$PATTERN" "$TRANSCRIPT" | sed 's/[:\[\]*]//g' | sort -u)

if [[ -z "$SPEAKERS" ]]; then
    echo "No speaker labels found."
    exit 0
fi

# Show context for each speaker
show_speaker_context() {
    local speaker="$1"
    local count=0
    
    while IFS= read -r line; do
        if [[ "$line" =~ $speaker ]]; then
            # Extract just the speech content
            content=$(echo "$line" | sed "s/.*$speaker[^:]*:\s*//" | head -c 200)
            if [[ -n "$content" ]]; then
                echo "  \"$content...\""
                ((count++))
                [[ $count -ge 3 ]] && break
            fi
        fi
    done < "$TRANSCRIPT"
}

declare -A SPEAKER_MAP

echo ""
for speaker in $SPEAKERS; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎤 $speaker"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    show_speaker_context "$speaker"
    echo ""
    read -p "Name for $speaker (Enter to skip): " name
    
    [[ -n "$name" ]] && SPEAKER_MAP["$speaker"]="$name"
done

# Show summary and confirm
if [[ ${#SPEAKER_MAP[@]} -eq 0 ]]; then
    echo "No changes to make."
    exit 0
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Changes to apply:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for speaker in "${!SPEAKER_MAP[@]}"; do
    echo "  $speaker → ${SPEAKER_MAP[$speaker]}"
done
echo ""
read -p "Proceed? [y/N] " confirm
[[ "$confirm" != [yY] ]] && exit 0

# Create backup
cp "$TRANSCRIPT" "${TRANSCRIPT}.bak"

# Apply changes with Perl for reliability
for speaker in "${!SPEAKER_MAP[@]}"; do
    name="${SPEAKER_MAP[$speaker]}"
    
    perl -i -pe "s/\Q$speaker\E/$name/g" "$TRANSCRIPT"
    [[ -f "$SUMMARY" ]] && perl -i -pe "s/\Q$speaker\E/$name/g" "$SUMMARY"
done

echo ""
echo "✓ Updated: $TRANSCRIPT"
[[ -f "$SUMMARY" ]] && echo "✓ Updated: $SUMMARY"
echo "✓ Backup:  ${TRANSCRIPT}.bak"
```

---

## 6. Complete Setup Checklist

### Prerequisites

```bash
# System packages
sudo apt install ffmpeg yad inotify-tools jq curl pulseaudio-utils

# Python packages (for Scriberr if running locally)
pip install --break-system-packages whisperx pyannote.audio

# Optional: Ollama for local summarisation
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
```

### Directory Structure

```
~/
├── bin/
│   ├── meeting-recorder.sh      # Linux recording GUI
│   ├── scriberr-watcher.sh      # File processing wrapper
│   ├── summarise-transcript.sh  # LLM summarisation
│   └── label-speakers.sh        # Speaker name replacement
├── recordings/
│   └── Mobile Recorder/     # Synced from Android + Linux recordings
│       └── .done/               # Processed files moved here
├── transcripts/                 # Output transcripts and summaries
│   ├── meeting-20250129-1430.md
│   └── meeting-20250129-1430.summary.md
└── .config/
    └── scriberr/
        └── config.yaml
```

### Environment Variables

Add to `~/.bashrc`:

```bash
# API Keys
export GROQ_API_KEY="gsk_..."
export ANTHROPIC_API_KEY="sk-ant-..."
export HF_TOKEN="hf_..."  # HuggingFace for diarisation models

# Summarisation config
export SUMMARY_MODEL="claude-sonnet-4-20250514"

# Add scripts to PATH
export PATH="$HOME/bin:$PATH"
```

### Systemd Service (Optional)

For running Scriberr watcher as a service:

**File: `~/.config/systemd/user/scriberr-watcher.service`**

```ini
[Unit]
Description=Scriberr Transcription Watcher
After=network.target

[Service]
Type=simple
ExecStart=%h/bin/scriberr-watcher.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

Enable:

```bash
systemctl --user daemon-reload
systemctl --user enable --now scriberr-watcher.service
```

---

## 7. Usage Summary

| Task | Command |
|------|---------|
| Record on Android | Open Mobile Recorder, tap record |
| Record on Linux | `meeting-recorder.sh` or click desktop icon |
| Check transcription status | `ls ~/transcripts/` |
| View pending files | `ls ~/recordings/*.mp3` |
| View processed files | `ls ~/recordings/.done/` |
| Manual summarisation | `summarise-transcript.sh ~/transcripts/file.md` |
| Label speakers | `label-speakers.sh ~/transcripts/file.md` |
| View logs | `tail -f ~/.local/log/scriberr.log` |

---

## 8. Cost Estimates

| Service | Rate | 1hr meeting |
|---------|------|-------------|
| Groq Whisper API | $0.04/hr | $0.04 |
| Claude Sonnet (summary) | ~$3/MTok | ~$0.02 |
| **Total per meeting** | | **~$0.06** |

For local processing (slower but free): use Whisper via Scriberr's local mode + Ollama for summarisation.

---

## 9. Troubleshooting

### Recording captures wrong device

```bash
# List available sources
pactl list sources short

# Set default source (microphone)
pactl set-default-source <source_name>

# Set default sink (speakers/headphones)
pactl set-default-sink <sink_name>
```

### Scriberr not transcribing

1. Check Scriberr is running: `curl http://localhost:8080/health`
2. Check API key: ensure `GROQ_API_KEY` is set
3. Check file permissions in input directory
4. Review logs: `journalctl --user -u scriberr-watcher -f`

### Diarisation not working

1. Ensure HuggingFace token is set: `echo $HF_TOKEN`
2. Accept model licenses at:
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0

### Summary generation fails

```bash
# Test API connectivity
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
```
