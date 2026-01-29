#!/bin/bash
# Claude Code summarization script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/db.sh"

load_config

PROMPT_FILE="$REPO_DIR/assets/summarisation-prompt.md"

# Usage
usage() {
    echo "Usage: $0 <transcript_file> <meeting_title>"
    echo ""
    echo "Summarize a labeled transcript using Claude Code."
    echo "Outputs markdown with meeting summary and action items."
    exit 1
}

# Check if transcript is labeled
check_labeled() {
    local transcript_file="$1"

    # Check YAML frontmatter for labeled: true or any speaker with a non-null name
    if grep -q "labeled: true" "$transcript_file"; then
        return 0
    fi

    # Check if any speaker has a name set
    if grep -A1 "^  - id:" "$transcript_file" | grep -q "name: [^n]"; then
        return 0
    fi

    echo "Warning: Transcript may not be fully labeled. Proceeding anyway..." >&2
    return 0
}

# Extract participants from transcript
get_participants() {
    local transcript_file="$1"

    # Extract speaker names from YAML
    grep -A1 "^  - id:" "$transcript_file" | grep "name:" | sed 's/.*name: //' | grep -v "null" | tr '\n' ', ' | sed 's/, $//'
}

# Get transcript date from filename or content
get_transcript_date() {
    local transcript_file="$1"

    # Try to extract from filename (format: YYYY-MM-DD-HH-MM-...)
    local basename=$(basename "$transcript_file")
    if [[ "$basename" =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2}) ]]; then
        echo "${BASH_REMATCH[1]}"
        return
    fi

    # Fall back to today's date
    date +%Y-%m-%d
}

# Generate summary filename
get_summary_filename() {
    local transcript_file="$1"
    local title="$2"

    local date=$(get_transcript_date "$transcript_file")
    local slug=$(echo "$title" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd 'a-z0-9-')

    echo "${date}-${slug}.md"
}

# Get relative path for wikilink
get_wikilink() {
    local transcript_file="$1"
    local basename=$(basename "$transcript_file" .yaml)
    echo "raw-transcription/$basename"
}

# Main
main() {
    if [[ $# -lt 2 ]]; then
        usage
    fi

    local transcript_file="$1"
    local title="$2"

    if [[ ! -f "$transcript_file" ]]; then
        echo "Error: Transcript file not found: $transcript_file" >&2
        exit 1
    fi

    if [[ ! -f "$PROMPT_FILE" ]]; then
        echo "Error: Prompt template not found: $PROMPT_FILE" >&2
        exit 1
    fi

    if ! command -v claude &>/dev/null; then
        echo "Error: claude CLI not found. Install Claude Code first." >&2
        exit 1
    fi

    init_db
    check_labeled "$transcript_file"

    local participants=$(get_participants "$transcript_file")
    local date=$(get_transcript_date "$transcript_file")
    local wikilink=$(get_wikilink "$transcript_file")
    local output_filename=$(get_summary_filename "$transcript_file" "$title")
    local output_file="$SUMMARIES_DIR/$output_filename"

    # Ensure output directory exists
    mkdir -p "$SUMMARIES_DIR"

    # Build the prompt
    local prompt=$(cat "$PROMPT_FILE")
    prompt="$prompt

Meeting Title: $title
Date: $date
Participants: $participants
Raw Transcript Link: [[$wikilink]]

--- BEGIN TRANSCRIPT ---
$(cat "$transcript_file")
--- END TRANSCRIPT ---"

    echo "Generating summary with Claude Code..." >&2

    # Call Claude Code
    local summary=$(echo "$prompt" | claude -p)

    # Write output file
    cat > "$output_file" <<EOF
---
date: $date
title: $title
participants: [$participants]
---

> Raw transcript: [[$wikilink]]

$summary
EOF

    echo "Summary saved to: $output_file" >&2

    # Update database
    db_mark_summarized "$transcript_file" "$output_file"

    echo "$output_file"
}

main "$@"
