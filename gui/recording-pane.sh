#!/bin/bash
# Recording controls pane
# Note: No set -e - GUI dialogs return non-zero on cancel which is normal

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$REPO_DIR/lib/config.sh"

load_config

# State files
RECORDING_STATE="/tmp/transcribe-recording-state"
RECORDING_PID="/tmp/transcribe-recording-pid"
RECORDING_FILE="/tmp/transcribe-recording-file"
RECORDING_START="/tmp/transcribe-recording-start"

# Check if recording is in progress
is_recording() {
    [[ -f "$RECORDING_STATE" ]]
}

# Get recording duration
get_duration() {
    if [[ -f "$RECORDING_START" ]]; then
        local start=$(cat "$RECORDING_START")
        local now=$(date +%s)
        local duration=$((now - start))
        printf "%02d:%02d:%02d" $((duration/3600)) $((duration%3600/60)) $((duration%60))
    else
        echo "00:00:00"
    fi
}

# Start recording
start_recording() {
    if is_recording; then
        echo "Recording already in progress!"
        return 1
    fi

    local filename="recording-$(date +%Y-%m-%d-%H-%M-%S).mp4"
    local output_file="$WATCH_DIR/$filename"

    mkdir -p "$WATCH_DIR"

    # Detect audio sources
    local mic_source="default"
    local sys_source=""

    # Try to find system audio monitor
    if command -v pactl &>/dev/null; then
        sys_source=$(pactl list short sources | grep -i monitor | head -1 | cut -f2)
    fi

    # Record with ffmpeg
    if [[ -n "$sys_source" ]]; then
        # Record both mic and system audio
        ffmpeg -f pulse -i "$mic_source" -f pulse -i "$sys_source" \
            -filter_complex amerge=inputs=2 -ac 2 \
            -y "$output_file" &>/dev/null &
    else
        # Record mic only
        ffmpeg -f pulse -i "$mic_source" -y "$output_file" &>/dev/null &
    fi

    local pid=$!

    echo "$pid" > "$RECORDING_PID"
    echo "$output_file" > "$RECORDING_FILE"
    date +%s > "$RECORDING_START"
    touch "$RECORDING_STATE"

    echo "Recording started: $filename"
    echo "PID: $pid"
}

# Stop recording
stop_recording() {
    if ! is_recording; then
        echo "No recording in progress!"
        return 1
    fi

    local output_file=""
    if [[ -f "$RECORDING_FILE" ]]; then
        output_file=$(cat "$RECORDING_FILE")
    fi

    if [[ -f "$RECORDING_PID" ]]; then
        local pid=$(cat "$RECORDING_PID")
        # Send SIGINT for clean shutdown
        kill -INT "$pid" 2>/dev/null || true
        sleep 2
        # Force kill if still running
        kill -9 "$pid" 2>/dev/null || true
    fi

    rm -f "$RECORDING_STATE" "$RECORDING_PID" "$RECORDING_FILE" "$RECORDING_START"

    if [[ -n "$output_file" && -f "$output_file" ]]; then
        local size=$(du -h "$output_file" | cut -f1)
        echo "Recording saved: $(basename "$output_file") ($size)"

        # Add to database
        source "$REPO_DIR/lib/db.sh"
        init_db
        db_add_audio "$output_file"
    else
        echo "Warning: Recording file not found"
    fi
}

# Status
show_status() {
    if is_recording; then
        echo "Status: RECORDING"
        echo "Duration: $(get_duration)"
        if [[ -f "$RECORDING_FILE" ]]; then
            echo "File: $(basename "$(cat "$RECORDING_FILE")")"
        fi
    else
        echo "Status: Idle"
    fi
}

# Interactive GUI
gui() {
    while true; do
        local status="Idle"
        local duration=""
        local btn_text="Start Recording"

        if is_recording; then
            status="● RECORDING"
            duration=$(get_duration)
            btn_text="Stop Recording"
        fi

        local action=$(zenity --list \
            --title="Recording" \
            --text="Status: $status\nDuration: $duration" \
            --column="Action" \
            --width=300 --height=200 \
            "$btn_text" \
            "Back to Menu")

        case "$action" in
            "Start Recording")
                start_recording
                zenity --info --text="Recording started!" --timeout=2
                ;;
            "Stop Recording")
                stop_recording
                zenity --info --text="Recording stopped and saved!"
                ;;
            "Back to Menu"|"")
                break
                ;;
        esac
    done
}

# CLI interface
case "${1:-gui}" in
    start)
        start_recording
        ;;
    stop)
        stop_recording
        ;;
    status)
        show_status
        ;;
    toggle)
        if is_recording; then
            stop_recording
        else
            start_recording
        fi
        ;;
    gui)
        gui
        ;;
    *)
        echo "Usage: $0 {start|stop|status|toggle|gui}"
        exit 1
        ;;
esac
