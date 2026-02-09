"""Tests for the command palette provider."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.app import TranscribeApp
from src.commands import TranscribeCommands
from src.screens.main_menu import MainMenuScreen
from src.screens.unified import UnifiedScreen


def _make_app(tmpdir: str) -> TranscribeApp:
    """Build a TranscribeApp with mocked backends."""
    mock_config = MagicMock()
    mock_config.db_file = Path(tmpdir) / "test.db"
    mock_config.watch_dir = Path(tmpdir) / "watch"
    mock_config.watch_dir.mkdir(exist_ok=True)
    mock_config.raw_transcripts_dir = Path(tmpdir) / "transcripts"
    mock_config.auto_process = False

    mock_db = MagicMock()
    mock_db.get_pending_count.return_value = 0
    mock_db.get_unlabeled_count.return_value = 0
    mock_db.list_unified.return_value = []
    mock_db.list_audio_files.return_value = []

    mock_recorder = MagicMock()
    mock_recorder.is_recording = False

    with (
        patch("src.app.Config", return_value=mock_config),
        patch("src.app.Database", return_value=mock_db),
        patch("src.app.Recorder", return_value=mock_recorder),
    ):
        return TranscribeApp()


class TestCommandPalette:
    """Tests for TranscribeCommands provider and palette integration."""

    @pytest.mark.asyncio
    async def test_command_palette_opens(self):
        """Ctrl+P opens the command palette overlay."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app = _make_app(tmpdir)
            async with app.run_test() as pilot:
                await pilot.press("ctrl+p")
                await pilot.pause()
                from textual.command import CommandPalette
                assert any(
                    isinstance(s, CommandPalette) for s in app.screen_stack
                )

    @pytest.mark.asyncio
    async def test_discover_commands(self):
        """discover() yields all expected commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app = _make_app(tmpdir)
            async with app.run_test() as pilot:
                provider = TranscribeCommands(app.screen)
                hits = [hit async for hit in provider.discover()]
                labels = [str(h.display) for h in hits]
                assert "Files & Labels" in labels
                assert "Recording" in labels
                assert "Edit Configuration" in labels
                assert "Toggle Auto-Process" in labels
                assert "Process All Pending" in labels
                assert "Refresh Files" in labels
                assert "Transcribe Selected" in labels
                assert "Generate Summary" in labels
                assert "Regenerate Summary" in labels
                assert "Save Labels" in labels
                assert "Open Watch Folder" in labels
                assert "Quit" in labels
                assert len(hits) == 12

    @pytest.mark.asyncio
    async def test_search_filters(self):
        """search() returns matching commands with scores."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app = _make_app(tmpdir)
            async with app.run_test() as pilot:
                provider = TranscribeCommands(app.screen)
                hits = [hit async for hit in provider.search("record")]
                texts = [h.help for h in hits]
                assert any("recording" in t.lower() for t in texts)
                assert all(h.score > 0 for h in hits)

    @pytest.mark.asyncio
    async def test_command_navigates_to_files(self):
        """Invoking 'Files & Labels' command navigates to UnifiedScreen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app = _make_app(tmpdir)
            async with app.run_test() as pilot:
                provider = TranscribeCommands(app.screen)
                hits = [hit async for hit in provider.discover()]
                files_hit = [h for h in hits if str(h.display) == "Files & Labels"][0]
                await files_hit.command()
                await pilot.pause()
                assert isinstance(app.screen, UnifiedScreen)

    @pytest.mark.asyncio
    async def test_command_quit(self):
        """Invoking 'Quit' command exits the app."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app = _make_app(tmpdir)
            async with app.run_test() as pilot:
                provider = TranscribeCommands(app.screen)
                hits = [hit async for hit in provider.discover()]
                quit_hit = [h for h in hits if str(h.display) == "Quit"][0]
                await quit_hit.command()
