#!/bin/bash
# File management pane
# Note: No set -e - GUI dialogs return non-zero on cancel which is normal

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

# Audio file extensions
AUDIO_EXTENSIONS="mp4|m4a|mp3|wav|ogg|webm|flac"

# Get audio files with status
get_files_list() {
    # First get from database
    local db_files=$(db_list_audio_files)

    # Build associative array of known files
    declare -A known_files

    if [[ -n "$db_files" ]]; then
        while IFS='|' read -r path filename status added; do
            known_files["$path"]=1
            if [[ -f "$path" ]]; then
                echo "$path|$filename|$status"
            fi
        done <<< "$db_files"
    fi

    # Check filesystem for files not in DB
    if [[ -d "$WATCH_DIR" ]]; then
        for file in "$WATCH_DIR"/*; do
            if [[ -f "$file" ]]; then
                local ext="${file##*.}"
                ext=$(echo "$ext" | tr '[:upper:]' '[:lower:]')
                if [[ "$ext" =~ ^($AUDIO_EXTENSIONS)$ ]]; then
                    if [[ -z "${known_files[$file]:-}" ]]; then
                        echo "$file|$(basename "$file")|pending"
                    fi
                fi
            fi
        done
    fi
}

# Transcribe a file
transcribe_file() {
    local file="$1"

    if [[ ! -f "$file" ]]; then
        echo "Error: File not found: $file" >&2
        return 1
    fi

    echo "Transcribing: $(basename "$file")"
    "$REPO_DIR/lib/transcribe-audio.sh" "$file"
}

# Delete a file
delete_file() {
    local file="$1"

    if [[ ! -f "$file" ]]; then
        echo "File already deleted: $file"
        return 0
    fi

    rm -f "$file"
    db_delete_audio "$file"
    echo "Deleted: $(basename "$file")"
}

# CLI list
list_files() {
    echo "Audio Files in: $WATCH_DIR"
    echo "============================================"

    local files=$(get_files_list)
    if [[ -z "$files" ]]; then
        echo "No audio files found."
        return 0
    fi

    printf "%-40s %s\n" "FILENAME" "STATUS"
    printf "%-40s %s\n" "--------" "------"

    while IFS='|' read -r path filename status; do
        local icon="○"
        case "$status" in
            transcribed) icon="✓" ;;
            pending) icon="○" ;;
            done) icon="●" ;;
        esac
        printf "%-40s %s %s\n" "$filename" "$icon" "$status"
    done <<< "$files"
}

# GUI mode
gui() {
    while true; do
        # Build file list for dialog
        local files_data=()
        local files_paths=()

        while IFS='|' read -r path filename status; do
            files_data+=("FALSE" "$filename" "$status")
            files_paths+=("$path")
        done < <(get_files_list)

        if [[ ${#files_paths[@]} -eq 0 ]]; then
            zenity --info --text="No audio files found in:\n$WATCH_DIR"
            return 0
        fi

        # Show file list
        local selection=$(zenity --list \
            --title="Audio Files" \
            --text="Audio files in: $WATCH_DIR" \
            --checklist \
            --column="Select" --column="Filename" --column="Status" \
            --width=600 --height=400 \
            --print-column=2 \
            "${files_data[@]}")

        if [[ -z "$selection" ]]; then
            return 0
        fi

        # Find selected file path
        local selected_file=""
        for i in "${!files_paths[@]}"; do
            if [[ "$(basename "${files_paths[$i]}")" == "$selection" ]]; then
                selected_file="${files_paths[$i]}"
                break
            fi
        done

        if [[ -z "$selected_file" ]]; then
            continue
        fi

        # Show action menu
        local action=$(zenity --list \
            --title="File Actions" \
            --text="Selected: $(basename "$selected_file")" \
            --column="Action" --column="Description" \
            --width=400 --height=250 \
            "transcribe" "Transcribe this file" \
            "delete" "Delete this file" \
            "open" "Open containing folder" \
            "back" "Back to file list")

        case "$action" in
            transcribe)
                (
                    echo "# Starting transcription..."
                    transcribe_file "$selected_file" 2>&1
                    echo ""
                    echo "# Done!"
                ) | zenity --text-info --title="Transcribing" --width=600 --height=400
                ;;
            delete)
                if zenity --question --text="Delete file?\n$(basename "$selected_file")"; then
                    delete_file "$selected_file"
                    zenity --info --text="File deleted." --timeout=2
                fi
                ;;
            open)
                xdg-open "$(dirname "$selected_file")" &
                ;;
            back|"")
                continue
                ;;
        esac
    done
}

# Refresh - scan for new files and add to DB
refresh() {
    echo "Scanning for new files..."

    local count=0
    for file in "$WATCH_DIR"/*; do
        if [[ -f "$file" ]]; then
            local ext="${file##*.}"
            ext=$(echo "$ext" | tr '[:upper:]' '[:lower:]')
            if [[ "$ext" =~ ^($AUDIO_EXTENSIONS)$ ]]; then
                if ! db_audio_exists "$file"; then
                    db_add_audio "$file"
                    echo "  Added: $(basename "$file")"
                    ((count++))
                fi
            fi
        fi
    done

    echo "Found $count new file(s)."
}

# Main
case "${1:-gui}" in
    list)
        list_files
        ;;
    refresh)
        refresh
        ;;
    transcribe)
        if [[ -z "$2" ]]; then
            echo "Usage: $0 transcribe <file>"
            exit 1
        fi
        transcribe_file "$2"
        ;;
    delete)
        if [[ -z "$2" ]]; then
            echo "Usage: $0 delete <file>"
            exit 1
        fi
        delete_file "$2"
        ;;
    gui)
        gui
        ;;
    *)
        echo "Usage: $0 {list|refresh|transcribe|delete|gui}"
        exit 1
        ;;
esac
