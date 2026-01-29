"""Tests for configuration management."""

import json
import tempfile
from pathlib import Path

import pytest

from src.core.config import Config


class TestConfig:
    """Tests for the Config class."""

    def test_expand_path_with_tilde(self):
        """Test that ~ is expanded to home directory."""
        path = "~/documents/file.txt"
        expanded = Config.expand_path(path)
        assert expanded.startswith(str(Path.home()))
        assert expanded.endswith("documents/file.txt")
        assert "~" not in expanded

    def test_expand_path_without_tilde(self):
        """Test that paths without ~ are unchanged."""
        path = "/absolute/path/file.txt"
        expanded = Config.expand_path(path)
        assert expanded == path

    def test_default_values(self):
        """Test that default values are returned when config file missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(config_dir=tmpdir)

            # Should return expanded default values
            assert config.get("auto_process") is True
            assert "watch_dir" in config.DEFAULT_CONFIG

    def test_config_init_creates_file(self):
        """Test that init() creates config file with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(config_dir=tmpdir)
            config.init()

            assert config.config_file.exists()

            with open(config.config_file) as f:
                data = json.load(f)
            assert "watch_dir" in data

    def test_get_set_config(self):
        """Test getting and setting config values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(config_dir=tmpdir)
            config.init()

            config.set("auto_process", False)
            assert config.get("auto_process") is False

            config.set("custom_key", "custom_value")
            assert config.get("custom_key") == "custom_value"

    def test_get_all_config(self):
        """Test getting all configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(config_dir=tmpdir)
            config.init()

            all_config = config.get_all()
            assert isinstance(all_config, dict)
            assert "watch_dir" in all_config

    def test_get_missing_key_returns_default(self):
        """Test that missing keys return provided default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(config_dir=tmpdir)

            result = config.get("nonexistent_key", "default_value")
            assert result == "default_value"

    def test_path_properties(self):
        """Test path property accessors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(config_dir=tmpdir)
            config.init()

            assert isinstance(config.watch_dir, Path)
            assert isinstance(config.raw_transcripts_dir, Path)
            assert isinstance(config.summaries_dir, Path)
            assert isinstance(config.done_dir, Path)

    def test_get_api_key_missing_file(self):
        """Test get_api_key returns None when file missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(config_dir=tmpdir)
            config.set("api_key_file", f"{tmpdir}/nonexistent.json")

            assert config.get_api_key() is None

    def test_get_api_key_from_file(self):
        """Test get_api_key reads from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            api_key_file = Path(tmpdir) / "apikey.json"
            api_key_file.write_text('{"assemblyai_api_key": "test-key-123"}')

            config = Config(config_dir=tmpdir)
            config.set("api_key_file", str(api_key_file))

            assert config.get_api_key() == "test-key-123"

    def test_auto_process_property(self):
        """Test auto_process boolean property."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(config_dir=tmpdir)
            config.init()

            assert config.auto_process is True

            config.set("auto_process", False)
            assert config.auto_process is False
