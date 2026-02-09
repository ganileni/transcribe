"""Tests for the Textual TUI application."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.app import TranscribeApp
from src.screens.main_menu import MainMenuScreen
from src.screens.unified import UnifiedScreen


class TestTranscribeApp:
    """Tests for the main application."""

    @pytest.fixture
    def app(self):
        """Create app with temporary config directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.app.Config") as mock_config_class:
                mock_config = MagicMock()
                mock_config.db_file = Path(tmpdir) / "test.db"
                mock_config.watch_dir = Path(tmpdir) / "watch"
                mock_config.watch_dir.mkdir()
                mock_config_class.return_value = mock_config

                with patch("src.app.Database") as mock_db_class:
                    mock_db = MagicMock()
                    mock_db_class.return_value = mock_db

                    with patch("src.app.Recorder") as mock_recorder_class:
                        mock_recorder = MagicMock()
                        mock_recorder.is_recording = False
                        mock_recorder_class.return_value = mock_recorder

                        app = TranscribeApp()
                        yield app


class TestMainMenuScreen:
    """Tests for the main menu screen."""

    @pytest.mark.asyncio
    async def test_main_menu_mounts(self):
        """Test that main menu screen mounts successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.app.Config") as mock_config_class:
                mock_config = MagicMock()
                mock_config.db_file = Path(tmpdir) / "test.db"
                mock_config.watch_dir = Path(tmpdir) / "watch"
                mock_config.watch_dir.mkdir()
                mock_config_class.return_value = mock_config

                with patch("src.app.Database") as mock_db_class:
                    mock_db = MagicMock()
                    mock_db.get_pending_count.return_value = 0
                    mock_db.get_unlabeled_count.return_value = 0
                    mock_db_class.return_value = mock_db

                    with patch("src.app.Recorder") as mock_recorder_class:
                        mock_recorder = MagicMock()
                        mock_recorder.is_recording = False
                        mock_recorder_class.return_value = mock_recorder

                        app = TranscribeApp()
                        async with app.run_test() as pilot:
                            # Should be on main menu
                            assert isinstance(app.screen, MainMenuScreen)

    @pytest.mark.asyncio
    async def test_navigate_to_files(self):
        """Test navigation to unified files & labels screen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.app.Config") as mock_config_class:
                mock_config = MagicMock()
                mock_config.db_file = Path(tmpdir) / "test.db"
                mock_config.watch_dir = Path(tmpdir) / "watch"
                mock_config.raw_transcripts_dir = Path(tmpdir) / "transcripts"
                mock_config.watch_dir.mkdir()
                mock_config_class.return_value = mock_config

                with patch("src.app.Database") as mock_db_class:
                    mock_db = MagicMock()
                    mock_db.get_pending_count.return_value = 0
                    mock_db.get_unlabeled_count.return_value = 0
                    mock_db.list_audio_files.return_value = []
                    mock_db.list_unified.return_value = []
                    mock_db_class.return_value = mock_db

                    with patch("src.app.Recorder") as mock_recorder_class:
                        mock_recorder = MagicMock()
                        mock_recorder.is_recording = False
                        mock_recorder_class.return_value = mock_recorder

                        app = TranscribeApp()
                        async with app.run_test() as pilot:
                            await pilot.press("f")
                            assert isinstance(app.screen, UnifiedScreen)

    @pytest.mark.asyncio
    async def test_toggle_recording_key(self):
        """Test that 'r' key toggles recording on main menu."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.app.Config") as mock_config_class:
                mock_config = MagicMock()
                mock_config.db_file = Path(tmpdir) / "test.db"
                mock_config.watch_dir = Path(tmpdir) / "watch"
                mock_config.watch_dir.mkdir()
                mock_config_class.return_value = mock_config

                with patch("src.app.Database") as mock_db_class:
                    mock_db = MagicMock()
                    mock_db.get_pending_count.return_value = 0
                    mock_db.get_unlabeled_count.return_value = 0
                    mock_db_class.return_value = mock_db

                    with patch("src.app.Recorder") as mock_recorder_class:
                        mock_recorder = MagicMock()
                        mock_recorder.is_recording = False
                        mock_recorder_class.return_value = mock_recorder

                        app = TranscribeApp()
                        async with app.run_test() as pilot:
                            # 'r' on main menu toggles recording, not navigates
                            await pilot.press("r")
                            # Should stay on main menu and toggle recording
                            assert isinstance(app.screen, MainMenuScreen)
                            mock_recorder.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_escape_goes_back(self):
        """Test that escape returns to previous screen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.app.Config") as mock_config_class:
                mock_config = MagicMock()
                mock_config.db_file = Path(tmpdir) / "test.db"
                mock_config.watch_dir = Path(tmpdir) / "watch"
                mock_config.raw_transcripts_dir = Path(tmpdir) / "transcripts"
                mock_config.watch_dir.mkdir()
                mock_config_class.return_value = mock_config

                with patch("src.app.Database") as mock_db_class:
                    mock_db = MagicMock()
                    mock_db.get_pending_count.return_value = 0
                    mock_db.get_unlabeled_count.return_value = 0
                    mock_db.list_audio_files.return_value = []
                    mock_db.list_unified.return_value = []
                    mock_db_class.return_value = mock_db

                    with patch("src.app.Recorder") as mock_recorder_class:
                        mock_recorder = MagicMock()
                        mock_recorder.is_recording = False
                        mock_recorder_class.return_value = mock_recorder

                        app = TranscribeApp()
                        async with app.run_test() as pilot:
                            # Go to files
                            await pilot.press("f")
                            assert isinstance(app.screen, UnifiedScreen)

                            # Press escape to go back
                            await pilot.press("escape")
                            assert isinstance(app.screen, MainMenuScreen)
