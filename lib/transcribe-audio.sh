#!/bin/bash
# AssemblyAI transcription script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/db.sh"

load_config

# Usage
usage() {
    echo "Usage: $0 <audio_file>"
    echo ""
    echo "Transcribe an audio file using AssemblyAI with speaker diarization."
    echo "Outputs YAML format with speaker labels and timestamps."
    exit 1
}

# Check dependencies
check_deps() {
    for cmd in curl jq ffmpeg; do
        if ! command -v "$cmd" &>/dev/null; then
            echo "Error: $cmd is required but not installed." >&2
            exit 1
        fi
    done
}

# Get API key
get_assemblyai_key() {
    local key=$(get_api_key)
    if [[ -z "$key" ]]; then
        echo "Error: AssemblyAI API key not found in $API_KEY_FILE" >&2
        echo "Expected JSON format: {\"assemblyai_api_key\": \"your-key-here\"}" >&2
        exit 1
    fi
    echo "$key"
}

# Upload audio file to AssemblyAI
upload_audio() {
    local file="$1"
    local api_key="$2"

    echo "Uploading audio file..." >&2

    local response=$(curl -s -X POST "https://api.assemblyai.com/v2/upload" \
        -H "Authorization: $api_key" \
        -H "Content-Type: application/octet-stream" \
        --data-binary @"$file")

    local upload_url=$(echo "$response" | jq -r '.upload_url // empty')

    if [[ -z "$upload_url" ]]; then
        echo "Error uploading file: $response" >&2
        exit 1
    fi

    echo "$upload_url"
}

# Start transcription
start_transcription() {
    local upload_url="$1"
    local api_key="$2"

    echo "Starting transcription with speaker diarization..." >&2

    local response=$(curl -s -X POST "https://api.assemblyai.com/v2/transcript" \
        -H "Authorization: $api_key" \
        -H "Content-Type: application/json" \
        -d "{
            \"audio_url\": \"$upload_url\",
            \"speaker_labels\": true
        }")

    local transcript_id=$(echo "$response" | jq -r '.id // empty')

    if [[ -z "$transcript_id" ]]; then
        echo "Error starting transcription: $response" >&2
        exit 1
    fi

    echo "$transcript_id"
}

# Poll for transcription completion
poll_transcription() {
    local transcript_id="$1"
    local api_key="$2"

    echo "Waiting for transcription to complete..." >&2

    while true; do
        local response=$(curl -s -X GET "https://api.assemblyai.com/v2/transcript/$transcript_id" \
            -H "Authorization: $api_key")

        local status=$(echo "$response" | jq -r '.status')

        case "$status" in
            completed)
                echo "$response"
                return 0
                ;;
            error)
                local error=$(echo "$response" | jq -r '.error')
                echo "Transcription error: $error" >&2
                exit 1
                ;;
            *)
                echo "  Status: $status" >&2
                sleep 5
                ;;
        esac
    done
}

# Convert AssemblyAI response to YAML
convert_to_yaml() {
    local response="$1"
    local source_file="$2"

    local duration=$(echo "$response" | jq -r '.audio_duration // 0')
    local utterances=$(echo "$response" | jq -r '.utterances // []')

    # Get unique speakers
    local speakers=$(echo "$utterances" | jq -r '[.[].speaker] | unique | .[]')

    # Generate YAML
    cat <<EOF
---
source_file: $(basename "$source_file")
transcribed: $(date -Iseconds)
duration_seconds: $duration
labeled: false
speakers:
EOF

    # Add speaker entries
    echo "$speakers" | while read -r speaker; do
        if [[ -n "$speaker" ]]; then
            echo "  - id: \"$speaker\""
            echo "    name: null"
        fi
    done

    echo "---"
    echo "utterances:"

    # Add utterances
    echo "$utterances" | jq -r '.[] | "  - speaker: \"\(.speaker)\"\n    start: \(.start / 1000)\n    end: \(.end / 1000)\n    text: \"\(.text | gsub("\""; "\\\""))\""'
}

# Main
main() {
    if [[ $# -lt 1 ]]; then
        usage
    fi

    local audio_file="$1"

    if [[ ! -f "$audio_file" ]]; then
        echo "Error: File not found: $audio_file" >&2
        exit 1
    fi

    check_deps
    init_db

    local api_key=$(get_assemblyai_key)

    # Add to database
    db_add_audio "$audio_file"

    # Upload and transcribe
    local upload_url=$(upload_audio "$audio_file" "$api_key")
    local transcript_id=$(start_transcription "$upload_url" "$api_key")
    local response=$(poll_transcription "$transcript_id" "$api_key")

    # Generate output filename
    local basename=$(basename "$audio_file" | sed 's/\.[^.]*$//')
    local timestamp=$(date +%Y-%m-%d-%H-%M)
    local output_file="$RAW_TRANSCRIPTS_DIR/${timestamp}-${basename}-transcript.yaml"

    # Ensure output directory exists
    mkdir -p "$RAW_TRANSCRIPTS_DIR"

    # Convert and save
    convert_to_yaml "$response" "$audio_file" > "$output_file"

    echo "Transcription saved to: $output_file" >&2

    # Update database
    db_mark_transcribed "$audio_file" "$output_file"
    local audio_id=$(db_get_audio_id "$audio_file")
    db_add_transcript "$output_file" "$audio_id"

    echo "$output_file"
}

main "$@"
