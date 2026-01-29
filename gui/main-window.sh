#!/bin/bash
# Main 3-pane GUI window for transcribe
# Note: No set -e here - GUI dialogs return non-zero on cancel which is normal

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Error handler
show_error() {
    zenity --error --text="$1" --width=400 2>/dev/null || echo "ERROR: $1" >&2
}

source "$REPO_DIR/lib/config.sh" || { show_error "Failed to load config.sh"; exit 1; }
source "$REPO_DIR/lib/db.sh" || { show_error "Failed to load db.sh"; exit 1; }

load_config || { show_error "Failed to load configuration"; exit 1; }
init_db || { show_error "Failed to initialize database"; exit 1; }

# Check for yad (preferred) or zenity
if command -v yad &>/dev/null; then
    GUI_TOOL="yad"
elif command -v zenity &>/dev/null; then
    GUI_TOOL="zenity"
else
    echo "Error: Neither yad nor zenity found. Install one of them." >&2
    exit 1
fi

# State file for recording
RECORDING_STATE="/tmp/transcribe-recording-state"
RECORDING_PID="/tmp/transcribe-recording-pid"
RECORDING_FILE="/tmp/transcribe-recording-file"

# Get audio files for display
get_audio_files_display() {
    local files=$(db_list_audio_files)
    if [[ -z "$files" ]]; then
        # Also check filesystem for files not in DB
        for file in "$WATCH_DIR"/*; do
            if [[ -f "$file" ]]; then
                local ext="${file##*.}"
                case "$ext" in
                    mp4|m4a|mp3|wav|ogg|webm|flac)
                        echo "FALSE|$file|$(basename "$file")|pending"
                        ;;
                esac
            fi
        done
    else
        echo "$files" | while IFS='|' read -r path filename status added; do
            echo "FALSE|$path|$filename|$status"
        done
    fi
}

# Get unlabeled transcripts for display
get_unlabeled_display() {
    local transcripts=$(db_get_unlabeled)

    if [[ -z "$transcripts" ]]; then
        # Check filesystem
        for file in "$RAW_TRANSCRIPTS_DIR"/*.yaml; do
            if [[ -f "$file" ]]; then
                if grep -q "labeled: false" "$file" 2>/dev/null; then
                    local speakers=$(grep -c "^  - id:" "$file" 2>/dev/null || echo "?")
                    echo "FALSE|$file|$(basename "$file")|$speakers speakers"
                fi
            fi
        done
    else
        while IFS= read -r path; do
            if [[ -f "$path" ]]; then
                local speakers=$(grep -c "^  - id:" "$path" 2>/dev/null || echo "?")
                echo "FALSE|$path|$(basename "$path")|$speakers speakers"
            fi
        done <<< "$transcripts"
    fi
}

# Recording functions
start_recording() {
    if [[ -f "$RECORDING_STATE" ]]; then
        zenity --error --text="Recording already in progress!"
        return 1
    fi

    local filename="recording-$(date +%Y-%m-%d-%H-%M-%S).mp4"
    local output_file="$WATCH_DIR/$filename"

    mkdir -p "$WATCH_DIR"

    # Start recording with ffmpeg (microphone + system audio)
    # Using PulseAudio default source
    ffmpeg -f pulse -i default -y "$output_file" &>/dev/null &
    local pid=$!

    echo "$pid" > "$RECORDING_PID"
    echo "$output_file" > "$RECORDING_FILE"
    touch "$RECORDING_STATE"

    zenity --info --text="Recording started.\nFile: $filename" --timeout=2
}

stop_recording() {
    if [[ ! -f "$RECORDING_STATE" ]]; then
        zenity --error --text="No recording in progress!"
        return 1
    fi

    if [[ -f "$RECORDING_PID" ]]; then
        local pid=$(cat "$RECORDING_PID")
        kill -INT "$pid" 2>/dev/null || true
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
    fi

    local output_file=""
    if [[ -f "$RECORDING_FILE" ]]; then
        output_file=$(cat "$RECORDING_FILE")
    fi

    rm -f "$RECORDING_STATE" "$RECORDING_PID" "$RECORDING_FILE"

    if [[ -n "$output_file" && -f "$output_file" ]]; then
        zenity --info --text="Recording saved to:\n$(basename "$output_file")"
        db_add_audio "$output_file"
    fi
}

# Label a transcript
label_transcript() {
    local transcript_file="$1"

    if [[ ! -f "$transcript_file" ]]; then
        zenity --error --text="Transcript file not found!"
        return 1
    fi

    "$SCRIPT_DIR/labeling-pane.sh" "$transcript_file"
}

# Transcribe selected file
transcribe_file() {
    local audio_file="$1"

    if [[ ! -f "$audio_file" ]]; then
        zenity --error --text="Audio file not found!"
        return 1
    fi

    (
        echo "10"
        echo "# Uploading audio file..."
        sleep 1

        echo "30"
        echo "# Transcribing with AssemblyAI..."

        local result=$("$REPO_DIR/lib/transcribe-audio.sh" "$audio_file" 2>&1)

        echo "100"
        echo "# Complete!"
    ) | zenity --progress --title="Transcribing" --auto-close --auto-kill

    zenity --info --text="Transcription complete!"
}

# Delete selected file
delete_file() {
    local file="$1"

    if zenity --question --text="Delete file?\n$(basename "$file")"; then
        rm -f "$file"
        db_delete_audio "$file"
        zenity --info --text="File deleted."
    fi
}

# Main menu using yad notebook or zenity tabs
main_gui() {
    while true; do
        # Build menu
        local action=$(zenity --list \
            --title="Transcribe" \
            --text="Meeting Transcription Manager" \
            --column="Action" --column="Description" \
            --width=500 --height=400 \
            "record" "Start/Stop Recording" \
            "files" "Manage Audio Files" \
            "label" "Label Transcripts" \
            "process" "Process All Recordings" \
            "config" "Edit Configuration" \
            "quit" "Exit")

        case "$action" in
            record)
                if [[ -f "$RECORDING_STATE" ]]; then
                    stop_recording
                else
                    start_recording
                fi
                ;;
            files)
                "$SCRIPT_DIR/files-pane.sh" gui || true
                ;;
            label)
                "$SCRIPT_DIR/labeling-pane.sh" || true
                ;;
            process)
                (
                    "$REPO_DIR/lib/process-recordings.sh" 2>&1
                ) | zenity --text-info --title="Processing" --width=600 --height=400 || true
                ;;
            config)
                ${EDITOR:-nano} "$CONFIG_FILE"
                load_config
                ;;
            quit|"")
                break
                ;;
        esac
    done
}

main_gui
