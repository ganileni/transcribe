"""Generate SVG screenshots of the Transcribe TUI for documentation."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.app import TranscribeApp
from src.screens.main_menu import MainMenuScreen
from src.screens.unified import UnifiedScreen

OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "screenshots"
TERMINAL_SIZE = (120, 36)


def _make_mock_app(tmpdir: str, db_mock: MagicMock | None = None) -> TranscribeApp:
    """Build a TranscribeApp with fully mocked Config/Database/Recorder."""
    mock_config = MagicMock()
    mock_config.db_file = Path(tmpdir) / "test.db"
    mock_config.watch_dir = Path(tmpdir) / "watch"
    mock_config.watch_dir.mkdir(exist_ok=True)
    mock_config.raw_transcripts_dir = Path(tmpdir) / "transcripts"
    mock_config.auto_process = True

    mock_db = db_mock or MagicMock()
    mock_db.get_pending_count.return_value = 3
    mock_db.get_unlabeled_count.return_value = 1
    mock_db.list_unified.return_value = []
    mock_db.list_audio_files.return_value = []

    mock_recorder = MagicMock()
    mock_recorder.is_recording = False
    mock_recorder.is_paused = False

    with (
        patch("src.app.Config", return_value=mock_config),
        patch("src.app.Database", return_value=mock_db),
        patch("src.app.Recorder", return_value=mock_recorder),
    ):
        return TranscribeApp()


def _save(name: str, svg: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    path.write_text(svg)
    print(f"  wrote {path}")


# -- Main Menu screenshot -----------------------------------------------------

async def _screenshot_main_menu() -> None:
    print("Generating main-menu.svg ...")
    with tempfile.TemporaryDirectory() as tmpdir:
        app = _make_mock_app(tmpdir)
        async with app.run_test(size=TERMINAL_SIZE) as pilot:
            await pilot.pause()
            svg = app.export_screenshot(title="Transcribe")
            _save("main-menu.svg", svg)


# -- Files & Labels screenshot ------------------------------------------------

MOCK_UNIFIED_ROWS = [
    {
        "type": "audio",
        "audio_path": "/tmp/recordings/standup-2026-02-03.mp4",
        "audio_filename": "standup-2026-02-03.mp4",
        "transcript_path": "/tmp/transcripts/standup-2026-02-03.yaml",
        "stage": "to label",
        "speakers": "Speaker A, Speaker B",
        "date": "2026-02-03",
        "duration_seconds": 1823,
        "name": "standup-2026-02-03",
    },
    {
        "type": "audio",
        "audio_path": "/tmp/recordings/interview-2026-02-05.mp4",
        "audio_filename": "interview-2026-02-05.mp4",
        "transcript_path": None,
        "stage": "to transcribe",
        "speakers": None,
        "date": "2026-02-05",
        "duration_seconds": 3604,
        "name": "interview-2026-02-05",
    },
    {
        "type": "audio",
        "audio_path": "/tmp/recordings/retro-2026-02-07.mp4",
        "audio_filename": "retro-2026-02-07.mp4",
        "transcript_path": "/tmp/transcripts/retro-2026-02-07.yaml",
        "stage": "summarised",
        "speakers": "Alice, Bob, Carol",
        "date": "2026-02-07",
        "duration_seconds": 2710,
        "name": "Weekly Retrospective",
    },
    {
        "type": "audio",
        "audio_path": "/tmp/recordings/planning-2026-02-09.m4a",
        "audio_filename": "planning-2026-02-09.m4a",
        "transcript_path": None,
        "stage": "to transcribe",
        "speakers": None,
        "date": "2026-02-09",
        "duration_seconds": None,
        "name": "planning-2026-02-09",
    },
]


async def _screenshot_files_labels() -> None:
    print("Generating files-labels.svg ...")
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_db = MagicMock()
        mock_db.get_pending_count.return_value = 2
        mock_db.get_unlabeled_count.return_value = 1
        mock_db.list_unified.return_value = MOCK_UNIFIED_ROWS

        app = _make_mock_app(tmpdir, db_mock=mock_db)
        async with app.run_test(size=TERMINAL_SIZE) as pilot:
            await pilot.press("f")
            await pilot.pause()
            svg = app.export_screenshot(title="Transcribe")
            _save("files-labels.svg", svg)


# -- Labeling screenshot ------------------------------------------------------

async def _screenshot_labeling() -> None:
    print("Generating labeling.svg ...")
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_db = MagicMock()
        mock_db.get_pending_count.return_value = 0
        mock_db.get_unlabeled_count.return_value = 1
        mock_db.list_unified.return_value = MOCK_UNIFIED_ROWS[:1]

        app = _make_mock_app(tmpdir, db_mock=mock_db)
        async with app.run_test(size=TERMINAL_SIZE) as pilot:
            await pilot.press("f")
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, UnifiedScreen)

            # Simulate a loaded transcript with 3 speakers at speaker 2 of 3
            from src.models import Speaker, TranscriptData, Utterance
            from datetime import datetime

            transcript = TranscriptData(
                source_file="standup-2026-02-03.mp4",
                transcribed=datetime(2026, 2, 3, 10, 0),
                duration_seconds=1823,
                labeled=False,
                speakers=[
                    Speaker(id="Speaker A", name="Alice"),
                    Speaker(id="Speaker B", name=None),
                    Speaker(id="Speaker C", name=None),
                ],
                utterances=[
                    Utterance("Speaker A", 0.0, 4.5, "Good morning everyone, shall we start with updates?"),
                    Utterance("Speaker B", 5.0, 12.3, "Sure, I finished the API refactor yesterday. Tests are green."),
                    Utterance("Speaker C", 13.0, 18.7, "I've been working on the dashboard redesign, almost done."),
                    Utterance("Speaker A", 19.0, 25.1, "Great progress. Any blockers?"),
                    Utterance("Speaker B", 25.5, 33.0, "I need a review on the migration PR before I can merge."),
                    Utterance("Speaker C", 33.5, 40.2, "No blockers from me. Should be ready for QA tomorrow."),
                ],
            )

            screen.current_transcript = transcript
            screen.current_transcript_path = Path("/tmp/transcripts/standup-2026-02-03.yaml")
            screen.current_speaker_index = 1  # Speaker 2 of 3
            screen.sample_count = 3
            screen._show_current_speaker()

            # Type a partial name into the input
            speaker_input = screen.query_one("#speaker-input")
            speaker_input.value = "Bo"

            await pilot.pause()
            svg = app.export_screenshot(title="Transcribe")
            _save("labeling.svg", svg)


async def main() -> None:
    await _screenshot_main_menu()
    await _screenshot_files_labels()
    await _screenshot_labeling()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
