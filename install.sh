#!/bin/bash
# Installation script for Transcribe

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/transcribe"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "Installing Transcribe..."
echo ""

# Check dependencies
echo "Checking dependencies..."
MISSING_DEPS=()

for cmd in ffmpeg jq curl sqlite3; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING_DEPS+=("$cmd")
    fi
done

# Check for Python 3.11+
if ! command -v python3 &>/dev/null; then
    MISSING_DEPS+=("python3")
else
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ "$(echo "$PY_VERSION >= 3.11" | bc)" != "1" ]]; then
        echo "  Warning: Python $PY_VERSION found, but 3.11+ recommended"
    fi
fi

# Check for inotifywait
if ! command -v inotifywait &>/dev/null; then
    MISSING_DEPS+=("inotify-tools (for inotifywait)")
fi

# Check for pactl (optional but recommended)
if ! command -v pactl &>/dev/null; then
    echo "  Warning: pactl not found. System audio recording may not work."
    echo "  Install pulseaudio-utils for full functionality."
fi

# Check for claude CLI
if ! command -v claude &>/dev/null; then
    echo "  Warning: claude CLI not found. Summarization will not work."
    echo "  Install Claude Code for summarization functionality."
fi

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo ""
    echo "Missing required dependencies:"
    for dep in "${MISSING_DEPS[@]}"; do
        echo "  - $dep"
    done
    echo ""
    echo "Install them with:"
    echo "  sudo apt install ffmpeg jq curl sqlite3 python3 python3-pip inotify-tools pulseaudio-utils"
    echo ""
    read -p "Continue anyway? [y/N]: " continue
    if [[ ! "$continue" =~ ^[Yy] ]]; then
        exit 1
    fi
fi
echo "  Dependencies OK"
echo ""

# Make scripts executable
echo "Setting permissions..."
chmod +x "$SCRIPT_DIR/transcribe"
chmod +x "$SCRIPT_DIR/lib/"*.sh
echo "  Done"
echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
if command -v pip3 &>/dev/null; then
    pip3 install --user -e "$SCRIPT_DIR" 2>/dev/null || pip3 install --user textual pyyaml requests
    echo "  Python packages installed"
else
    echo "  Warning: pip3 not found. Install Python dependencies manually:"
    echo "    pip install textual pyyaml requests"
fi
echo ""

# Create config directory and initialize
echo "Creating configuration..."
mkdir -p "$CONFIG_DIR"

if [[ ! -f "$CONFIG_DIR/config.json" ]]; then
    cat > "$CONFIG_DIR/config.json" <<'EOF'
{
  "watch_dir": "~/recordings",
  "raw_transcripts_dir": "~/transcripts/raw",
  "summaries_dir": "~/transcripts/summaries",
  "done_dir": "~/recordings/.done",
  "api_key_file": "~/.transcribe.apikey.json",
  "auto_process": true
}
EOF
    echo "  Created default config: $CONFIG_DIR/config.json"
else
    echo "  Config already exists: $CONFIG_DIR/config.json"
fi

# Initialize database
source "$SCRIPT_DIR/lib/db.sh"
init_db
echo "  Database initialized: $CONFIG_DIR/transcribe.db"
echo ""

# Create symlink in ~/.local/bin
echo "Creating symlink..."
mkdir -p "$BIN_DIR"
ln -sf "$SCRIPT_DIR/transcribe" "$BIN_DIR/transcribe"
echo "  Created: $BIN_DIR/transcribe -> $SCRIPT_DIR/transcribe"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "  Note: $BIN_DIR is not in your PATH."
    echo "  Add this to your ~/.bashrc or ~/.zshrc:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
echo ""

# Optional: Desktop file
read -p "Create desktop launcher? [y/N]: " create_desktop
if [[ "$create_desktop" =~ ^[Yy] ]]; then
    mkdir -p "$DESKTOP_DIR"
    cat > "$DESKTOP_DIR/transcribe.desktop" <<EOF
[Desktop Entry]
Name=Transcribe
Comment=Meeting Transcription Application
Exec=$SCRIPT_DIR/transcribe gui
Icon=audio-input-microphone
Terminal=true
Type=Application
Categories=Utility;AudioVideo;
Keywords=transcribe;meeting;audio;record;
EOF
    echo "  Created: $DESKTOP_DIR/transcribe.desktop"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi
echo ""

# Optional: Systemd service
read -p "Install systemd watcher service? [y/N]: " install_service
if [[ "$install_service" =~ ^[Yy] ]]; then
    mkdir -p "$SYSTEMD_DIR"

    cat > "$SYSTEMD_DIR/transcribe-watcher.service" <<EOF
[Unit]
Description=Transcribe - Watch for new recordings
After=network.target

[Service]
Type=simple
ExecStart=$SCRIPT_DIR/transcribe watch
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF
    echo "  Created: $SYSTEMD_DIR/transcribe-watcher.service"

    read -p "Enable and start the service now? [y/N]: " enable_service
    if [[ "$enable_service" =~ ^[Yy] ]]; then
        systemctl --user daemon-reload
        systemctl --user enable transcribe-watcher.service
        systemctl --user start transcribe-watcher.service
        echo "  Service enabled and started"
    fi
fi
echo ""

# API key setup
echo "API Key Setup"
echo "============="
API_KEY_FILE="$HOME/.transcribe.apikey.json"
if [[ ! -f "$API_KEY_FILE" ]]; then
    echo "AssemblyAI API key not found."
    echo "Create $API_KEY_FILE with:"
    echo '  {"assemblyai_api_key": "your-key-here"}'
    echo ""
    read -p "Enter your AssemblyAI API key (or press Enter to skip): " api_key
    if [[ -n "$api_key" ]]; then
        echo "{\"assemblyai_api_key\": \"$api_key\"}" > "$API_KEY_FILE"
        chmod 600 "$API_KEY_FILE"
        echo "  Created: $API_KEY_FILE"
    fi
else
    echo "  API key file exists: $API_KEY_FILE"
fi
echo ""

echo "Installation complete!"
echo ""
echo "Quick start:"
echo "  transcribe gui        # Launch TUI (Terminal User Interface)"
echo "  transcribe status     # Show status"
echo "  transcribe config     # Edit configuration"
echo "  transcribe --help     # Show all commands"
echo ""
echo "Make sure to edit the configuration to match your directories."
