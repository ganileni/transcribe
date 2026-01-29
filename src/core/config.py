"""Configuration management for the Transcribe application."""

import json
import os
from pathlib import Path
from typing import Any


class Config:
    """Manages application configuration."""

    DEFAULT_CONFIG = {
        "watch_dir": "~/recordings",
        "raw_transcripts_dir": "~/transcripts/raw",
        "summaries_dir": "~/transcripts/summaries",
        "done_dir": "~/recordings/.done",
        "api_key_file": "~/.transcribe.apikey.json",
        "auto_process": True,
    }

    def __init__(self, config_dir: str | Path | None = None):
        """Initialize configuration.

        Args:
            config_dir: Custom config directory. Defaults to XDG_CONFIG_HOME/transcribe.
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
            self.config_dir = Path(xdg_config) / "transcribe"

        self.config_file = self.config_dir / "config.json"
        self.db_file = self.config_dir / "transcribe.db"
        self._config: dict[str, Any] = {}
        self._load()

    @staticmethod
    def expand_path(path: str) -> str:
        """Expand ~ to home directory in a path."""
        if path.startswith("~"):
            return str(Path.home()) + path[1:]
        return path

    def _ensure_config_dir(self) -> None:
        """Ensure the config directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """Load configuration from file, using defaults if not present."""
        if self.config_file.exists():
            with open(self.config_file) as f:
                self._config = json.load(f)
        else:
            self._config = self.DEFAULT_CONFIG.copy()

    def init(self) -> None:
        """Initialize config file with defaults if missing."""
        self._ensure_config_dir()
        if not self.config_file.exists():
            self.save()

    def save(self) -> None:
        """Save current configuration to file."""
        self._ensure_config_dir()
        with open(self.config_file, "w") as f:
            json.dump(self._config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by key, with path expansion.

        Args:
            key: The configuration key.
            default: Default value if key not found.

        Returns:
            The configuration value with paths expanded.
        """
        value = self._config.get(key, self.DEFAULT_CONFIG.get(key, default))
        if isinstance(value, str):
            return self.expand_path(value)
        return value

    def set(self, key: str, value: Any) -> None:
        """Set a config value.

        Args:
            key: The configuration key.
            value: The value to set.
        """
        self._config[key] = value
        self.save()

    def get_all(self) -> dict[str, Any]:
        """Get all configuration as a dictionary."""
        return self._config.copy()

    def get_api_key(self) -> str | None:
        """Get the AssemblyAI API key.

        Returns:
            The API key or None if not found.
        """
        key_file = Path(self.get("api_key_file"))
        if key_file.exists():
            with open(key_file) as f:
                data = json.load(f)
                return data.get("assemblyai_api_key") or data.get("api_key")
        return None

    @property
    def watch_dir(self) -> Path:
        """Get the watch directory path."""
        return Path(self.get("watch_dir"))

    @property
    def raw_transcripts_dir(self) -> Path:
        """Get the raw transcripts directory path."""
        return Path(self.get("raw_transcripts_dir"))

    @property
    def summaries_dir(self) -> Path:
        """Get the summaries directory path."""
        return Path(self.get("summaries_dir"))

    @property
    def done_dir(self) -> Path:
        """Get the done directory path."""
        return Path(self.get("done_dir"))

    @property
    def auto_process(self) -> bool:
        """Get the auto-process setting."""
        return bool(self.get("auto_process", True))
