#!/bin/bash
# File watcher for automatic transcription

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/db.sh"

load_config

# Check dependencies
if ! command -v inotifywait &>/dev/null; then
    echo "Error: inotifywait not found. Install inotify-tools." >&2
    exit 1
fi

echo "Watching for new recordings in: $WATCH_DIR"
echo "Press Ctrl+C to stop."

# Create watch directory if needed
mkdir -p "$WATCH_DIR"

# Watch for new files
inotifywait -m -e close_write -e moved_to "$WATCH_DIR" --format '%w%f' | while read -r file; do
    # Small delay to ensure file is fully written
    sleep 1

    # Check if it's an audio file
    ext="${file##*.}"
    ext=$(echo "$ext" | tr '[:upper:]' '[:lower:]')

    case "$ext" in
        mp4|m4a|mp3|wav|ogg|webm|flac)
            echo "New recording detected: $(basename "$file")"

            if [[ "$AUTO_PROCESS" == "true" ]]; then
                echo "Auto-processing enabled, starting transcription..."
                "$SCRIPT_DIR/process-recordings.sh"
            else
                echo "Auto-processing disabled. Run 'transcribe process' to transcribe."
            fi
            ;;
    esac
done
