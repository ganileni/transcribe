#!/bin/bash
# Configuration management for transcribe

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/transcribe"
CONFIG_FILE="$CONFIG_DIR/config.json"
DB_FILE="$CONFIG_DIR/transcribe.db"

# Default configuration
DEFAULT_CONFIG='{
  "watch_dir": "~/recordings",
  "raw_transcripts_dir": "~/transcripts/raw",
  "summaries_dir": "~/transcripts/summaries",
  "done_dir": "~/recordings/.done",
  "api_key_file": "~/.transcribe.apikey.json",
  "auto_process": true
}'

# Expand ~ to $HOME in a path
expand_path() {
    local path="$1"
    echo "${path/#\~/$HOME}"
}

# Ensure config directory exists
ensure_config_dir() {
    mkdir -p "$CONFIG_DIR"
}

# Initialize config file with defaults if missing
init_config() {
    ensure_config_dir
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo "$DEFAULT_CONFIG" > "$CONFIG_FILE"
    fi
}

# Get a config value by key
get_config() {
    local key="$1"
    local value

    if [[ ! -f "$CONFIG_FILE" ]]; then
        value=$(echo "$DEFAULT_CONFIG" | jq -r ".$key // empty")
    else
        value=$(jq -r ".$key // empty" "$CONFIG_FILE")
    fi

    # Expand paths
    expand_path "$value"
}

# Set a config value
set_config() {
    local key="$1"
    local value="$2"

    ensure_config_dir
    init_config

    local tmp=$(mktemp)
    jq ".$key = \"$value\"" "$CONFIG_FILE" > "$tmp" && mv "$tmp" "$CONFIG_FILE"
}

# Get all config as JSON (with expanded paths)
get_all_config() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo "$DEFAULT_CONFIG"
    else
        cat "$CONFIG_FILE"
    fi
}

# Load config into environment variables
load_config() {
    WATCH_DIR=$(get_config "watch_dir")
    RAW_TRANSCRIPTS_DIR=$(get_config "raw_transcripts_dir")
    SUMMARIES_DIR=$(get_config "summaries_dir")
    DONE_DIR=$(get_config "done_dir")
    API_KEY_FILE=$(get_config "api_key_file")
    AUTO_PROCESS=$(get_config "auto_process")

    export WATCH_DIR RAW_TRANSCRIPTS_DIR SUMMARIES_DIR DONE_DIR API_KEY_FILE AUTO_PROCESS
}

# Get AssemblyAI API key
get_api_key() {
    local key_file=$(get_config "api_key_file")
    if [[ -f "$key_file" ]]; then
        jq -r '.assemblyai_api_key // .api_key // empty' "$key_file"
    fi
}
