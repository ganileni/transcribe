#!/bin/bash
# Uninstallation script for Transcribe

set -e

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/transcribe"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "Uninstalling Transcribe..."
echo ""

# Stop and disable systemd service if running
if [[ -f "$SYSTEMD_DIR/transcribe-watcher.service" ]]; then
    echo "Stopping systemd service..."
    systemctl --user stop transcribe-watcher.service 2>/dev/null || true
    systemctl --user disable transcribe-watcher.service 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/transcribe-watcher.service"
    systemctl --user daemon-reload
    echo "  Removed systemd service"
fi

# Remove symlink
if [[ -L "$BIN_DIR/transcribe" ]]; then
    rm -f "$BIN_DIR/transcribe"
    echo "  Removed symlink: $BIN_DIR/transcribe"
fi

# Remove desktop file
if [[ -f "$DESKTOP_DIR/transcribe.desktop" ]]; then
    rm -f "$DESKTOP_DIR/transcribe.desktop"
    echo "  Removed desktop file: $DESKTOP_DIR/transcribe.desktop"
fi

# Clean up any recording state files
rm -f /tmp/transcribe-recording-*
echo "  Cleaned up temporary files"

echo ""

# Ask about config removal
if [[ -d "$CONFIG_DIR" ]]; then
    echo "Configuration directory: $CONFIG_DIR"
    echo "Contains:"
    ls -la "$CONFIG_DIR" 2>/dev/null || true
    echo ""
    read -p "Remove configuration and database? [y/N]: " remove_config
    if [[ "$remove_config" =~ ^[Yy] ]]; then
        rm -rf "$CONFIG_DIR"
        echo "  Removed: $CONFIG_DIR"
    else
        echo "  Kept: $CONFIG_DIR"
    fi
fi

echo ""
echo "Uninstallation complete."
echo ""
echo "Note: The repository files were not removed."
echo "Delete manually if needed: $(dirname "$0")"
