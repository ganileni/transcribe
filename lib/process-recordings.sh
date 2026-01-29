#!/bin/bash
# Batch processor for recordings

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/db.sh"

load_config

# Audio file extensions to process
AUDIO_EXTENSIONS=("mp4" "m4a" "mp3" "wav" "ogg" "webm" "flac")

# Check if file has audio extension
is_audio_file() {
    local file="$1"
    local ext="${file##*.}"
    ext=$(echo "$ext" | tr '[:upper:]' '[:lower:]')

    for valid_ext in "${AUDIO_EXTENSIONS[@]}"; do
        if [[ "$ext" == "$valid_ext" ]]; then
            return 0
        fi
    done
    return 1
}

# Get list of unprocessed audio files
get_unprocessed_files() {
    local watch_dir="$1"

    if [[ ! -d "$watch_dir" ]]; then
        echo "Error: Watch directory does not exist: $watch_dir" >&2
        return 1
    fi

    for file in "$watch_dir"/*; do
        if [[ -f "$file" ]] && is_audio_file "$file"; then
            if ! db_is_transcribed "$file"; then
                echo "$file"
            fi
        fi
    done
}

# Process a single file
process_file() {
    local file="$1"

    echo "Processing: $(basename "$file")"

    # Transcribe
    local transcript=$("$SCRIPT_DIR/transcribe-audio.sh" "$file")

    if [[ -n "$transcript" ]]; then
        echo "  Transcribed to: $transcript"

        # Move original to done directory
        mkdir -p "$DONE_DIR"
        mv "$file" "$DONE_DIR/"
        echo "  Moved original to: $DONE_DIR/"
    else
        echo "  Error: Transcription failed"
        return 1
    fi
}

# Main
main() {
    init_db

    echo "Scanning for unprocessed recordings in: $WATCH_DIR"
    echo ""

    local files=$(get_unprocessed_files "$WATCH_DIR")

    if [[ -z "$files" ]]; then
        echo "No unprocessed recordings found."
        exit 0
    fi

    local count=0
    while IFS= read -r file; do
        if [[ -n "$file" ]]; then
            process_file "$file" && ((count++)) || true
            echo ""
        fi
    done <<< "$files"

    echo "Processed $count file(s)."
}

main "$@"
