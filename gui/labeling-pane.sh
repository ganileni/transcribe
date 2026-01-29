#!/bin/bash
# Speaker labeling pane
# Note: No set -e - GUI dialogs return non-zero on cancel which is normal

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Error handler for unexpected errors
show_error() {
    zenity --error --text="$1" --width=400 2>/dev/null || echo "ERROR: $1" >&2
}

# Source dependencies with error checking
if ! source "$REPO_DIR/lib/config.sh" 2>/dev/null; then
    show_error "Failed to load config.sh"
    exit 1
fi

if ! source "$REPO_DIR/lib/db.sh" 2>/dev/null; then
    show_error "Failed to load db.sh"
    exit 1
fi

load_config || { show_error "Failed to load configuration"; exit 1; }
init_db || { show_error "Failed to initialize database"; exit 1; }

# Get sample utterances for a speaker
get_speaker_samples() {
    local transcript_file="$1"
    local speaker_id="$2"
    local num_samples="${3:-3}"

    # Extract utterances for this speaker
    awk -v speaker="$speaker_id" '
        /^  - speaker:/ {
            if (index($0, "\"" speaker "\"") > 0) {
                in_speaker = 1
            } else {
                in_speaker = 0
            }
        }
        /^    text:/ && in_speaker {
            gsub(/^    text: "/, "")
            gsub(/"$/, "")
            print
            count++
            if (count >= '"$num_samples"') exit
        }
    ' "$transcript_file"
}

# Get list of speakers from transcript
get_speakers() {
    local transcript_file="$1"

    # Extract speaker IDs from YAML
    grep -E "^  - id:" "$transcript_file" | sed 's/.*id: "\?\([^"]*\)"\?/\1/'
}

# Get participants (speaker names) from transcript
get_participants() {
    local transcript_file="$1"
    grep -A1 "^  - id:" "$transcript_file" | grep "name:" | sed 's/.*name: //' | grep -v "null" | tr -d '"' | tr '\n' ',' | sed 's/,$//'
}

# Get current speaker name
get_speaker_name() {
    local transcript_file="$1"
    local speaker_id="$2"

    # Look for name after the matching id
    awk -v id="$speaker_id" '
        /^  - id:/ {
            if (index($0, "\"" id "\"") > 0 || index($0, id) > 0) {
                getline
                if (/name:/) {
                    gsub(/.*name: /, "")
                    gsub(/"/, "")
                    if ($0 != "null" && $0 != "") print $0
                }
            }
        }
    ' "$transcript_file"
}

# Update speaker name in transcript
update_speaker_name() {
    local transcript_file="$1"
    local speaker_id="$2"
    local new_name="$3"

    # Create temp file
    local tmp=$(mktemp)

    # Update the YAML - find the speaker id and update the following name line
    awk -v id="$speaker_id" -v name="$new_name" '
        /^  - id:/ && (index($0, "\"" id "\"") > 0 || index($0, id) > 0) {
            print
            getline
            if (/name:/) {
                print "    name: \"" name "\""
                next
            }
        }
        { print }
    ' "$transcript_file" > "$tmp"

    mv "$tmp" "$transcript_file"
}

# Replace speaker IDs with names in utterances
replace_speaker_ids() {
    local transcript_file="$1"

    # Build sed script from speaker mappings
    local sed_script=""
    while IFS= read -r speaker_id; do
        local name=$(get_speaker_name "$transcript_file" "$speaker_id")
        if [[ -n "$name" && "$name" != "null" ]]; then
            sed_script="${sed_script}s/speaker: \"$speaker_id\"/speaker: \"$name\"/g;"
        fi
    done < <(get_speakers "$transcript_file")

    if [[ -n "$sed_script" ]]; then
        local tmp=$(mktemp)
        sed "$sed_script" "$transcript_file" > "$tmp"
        mv "$tmp" "$transcript_file"
    fi
}

# Mark transcript as labeled
mark_labeled() {
    local transcript_file="$1"

    # Update labeled: false to labeled: true in frontmatter
    sed -i 's/^labeled: false/labeled: true/' "$transcript_file"

    # Update database
    db_mark_labeled "$transcript_file"
}

# Label a single transcript
label_transcript() {
    local transcript_file="$1"

    if [[ ! -f "$transcript_file" ]]; then
        echo "Error: File not found: $transcript_file" >&2
        return 1
    fi

    echo "Labeling: $(basename "$transcript_file")"
    echo ""

    local speakers=$(get_speakers "$transcript_file")
    local all_labeled=true

    while IFS= read -r speaker_id; do
        if [[ -z "$speaker_id" ]]; then
            continue
        fi

        local current_name=$(get_speaker_name "$transcript_file" "$speaker_id")

        echo "=== $speaker_id ==="

        # Show sample utterances
        echo "Sample utterances:"
        get_speaker_samples "$transcript_file" "$speaker_id" | while read -r line; do
            echo "  \"$line\""
        done
        echo ""

        # Prompt for name
        local new_name
        if [[ -n "$current_name" && "$current_name" != "null" ]]; then
            read -p "Name [$current_name]: " new_name
            new_name="${new_name:-$current_name}"
        else
            read -p "Name for $speaker_id: " new_name
        fi

        if [[ -n "$new_name" ]]; then
            update_speaker_name "$transcript_file" "$speaker_id" "$new_name"
            echo "  → Set to: $new_name"
        else
            all_labeled=false
        fi
        echo ""
    done <<< "$speakers"

    # Replace speaker IDs with names in utterances
    replace_speaker_ids "$transcript_file"

    # Mark as labeled if all speakers have names
    if $all_labeled; then
        mark_labeled "$transcript_file"
        echo "Transcript marked as labeled."

        # Ask about summarization
        read -p "Generate summary now? [y/N]: " do_summary
        if [[ "$do_summary" =~ ^[Yy] ]]; then
            read -p "Meeting title: " title
            if [[ -n "$title" ]]; then
                "$REPO_DIR/lib/summarise-transcript.sh" "$transcript_file" "$title"
            fi
        fi
    fi
}

# GUI mode - select and label transcript
gui() {
    # Get unlabeled transcripts
    local transcripts=()
    local display=()

    while IFS= read -r path; do
        if [[ -f "$path" ]]; then
            transcripts+=("$path")
            local speakers=$(grep -c "^  - id:" "$path" 2>/dev/null || echo "?")
            display+=("FALSE" "$(basename "$path")" "$speakers speakers")
        fi
    done < <(db_get_unlabeled)

    # Also check filesystem for any not in DB
    for file in "$RAW_TRANSCRIPTS_DIR"/*.yaml; do
        if [[ -f "$file" ]] && grep -q "labeled: false" "$file" 2>/dev/null; then
            if [[ ! " ${transcripts[*]} " =~ " $file " ]]; then
                transcripts+=("$file")
                local speakers=$(grep -c "^  - id:" "$file" 2>/dev/null || echo "?")
                display+=("FALSE" "$(basename "$file")" "$speakers speakers")
            fi
        fi
    done

    if [[ ${#transcripts[@]} -eq 0 ]]; then
        zenity --info --text="No unlabeled transcripts found."
        return 0
    fi

    # Show selection dialog
    local selection=$(zenity --list \
        --title="Unlabeled Transcripts" \
        --text="Select a transcript to label:" \
        --checklist \
        --column="Select" --column="Filename" --column="Speakers" \
        --width=500 --height=400 \
        "${display[@]}")

    if [[ -z "$selection" ]]; then
        return 0
    fi

    # Find selected file
    local selected_file=""
    for file in "${transcripts[@]}"; do
        if [[ "$(basename "$file")" == "$selection" ]]; then
            selected_file="$file"
            break
        fi
    done

    if [[ -z "$selected_file" ]]; then
        return 0
    fi

    # Get speakers and label each one
    local speakers=$(get_speakers "$selected_file")
    if [[ -z "$speakers" ]]; then
        zenity --error --text="No speakers found in transcript file."
        return 1
    fi

    local all_labeled=true

    while IFS= read -r speaker_id; do
        if [[ -z "$speaker_id" ]]; then
            continue
        fi

        # Get samples and truncate each to ~80 chars, max 3 samples
        local samples=""
        while IFS= read -r line; do
            if [[ -n "$line" ]]; then
                # Truncate long lines
                if [[ ${#line} -gt 80 ]]; then
                    line="${line:0:77}..."
                fi
                samples="${samples}• ${line}\n"
            fi
        done < <(get_speaker_samples "$selected_file" "$speaker_id" 3)

        local current=$(get_speaker_name "$selected_file" "$speaker_id")

        # Show entry dialog for this speaker
        local new_name=$(zenity --entry \
            --title="Label Speaker: $speaker_id" \
            --text="Sample utterances:\n${samples}\nEnter name for $speaker_id:" \
            --entry-text="${current:-}" \
            --width=500)

        if [[ -n "$new_name" ]]; then
            update_speaker_name "$selected_file" "$speaker_id" "$new_name" || {
                zenity --error --text="Failed to update speaker name for $speaker_id"
                return 1
            }
        else
            all_labeled=false
        fi
    done <<< "$speakers"

    if ! $all_labeled; then
        zenity --warning --text="Not all speakers were labeled."
        return 0
    fi

    replace_speaker_ids "$selected_file"
    mark_labeled "$selected_file"

    zenity --info --text="Transcript labeled successfully!"

    # Auto-generate title from date and participants
    local date=$(basename "$selected_file" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' || date +%Y-%m-%d)
    local participants=$(get_participants "$selected_file" | tr ',' ' ' | xargs | tr ' ' '-')
    local auto_title="Meeting ${date}"
    if [[ -n "$participants" ]]; then
        auto_title="${date} ${participants}"
    fi

    # Ask about summarization with auto-generated title
    if zenity --question --text="Generate summary now?"; then
        local title=$(zenity --entry \
            --title="Meeting Title" \
            --text="Enter meeting title (or accept suggested):" \
            --entry-text="$auto_title" \
            --width=400)
        if [[ -n "$title" ]]; then
            (
                "$REPO_DIR/lib/summarise-transcript.sh" "$selected_file" "$title" 2>&1
            ) | zenity --text-info --title="Generating Summary" --width=600 --height=400
        fi
    fi
}

# Main
case "${1:-}" in
    "")
        gui
        ;;
    *.yaml)
        label_transcript "$1"
        ;;
    *)
        if [[ -f "$1" ]]; then
            label_transcript "$1"
        else
            echo "Usage: $0 [transcript.yaml]"
            echo "       $0  (GUI mode)"
            exit 1
        fi
        ;;
esac
