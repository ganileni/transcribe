"""Files screen for Transcribe TUI."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, LoadingIndicator

from ..core import Transcriber
from ..models import AudioFile


class FilesScreen(Screen):
    """File management screen with audio file list and actions."""

    BINDINGS = [
        ("t", "transcribe_selected", "Transcribe"),
        ("d", "delete_selected", "Delete"),
        ("r", "refresh", "Refresh"),
        ("o", "open_folder", "Open Folder"),
        ("escape", "go_back", "Back"),
    ]

    AUDIO_EXTENSIONS = {"mp4", "m4a", "mp3", "wav", "ogg", "webm", "flac"}

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="files-container"):
            yield Label("Audio Files", classes="title")
            yield DataTable(id="files-table")
            with Horizontal(id="files-actions"):
                yield Button("\\[T]ranscribe", id="transcribe-btn", variant="primary")
                yield Button("\\[D]elete", id="delete-btn", variant="error")
                yield Button("\\[R]efresh", id="refresh-btn")
                yield Button("\\[O]pen Folder", id="open-btn")
                yield Button("\\[B]ack", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        table = self.query_one("#files-table", DataTable)
        table.add_columns("Filename", "Stage", "Added")
        table.cursor_type = "row"
        self._refresh_table()
        self.set_interval(60.0, self._refresh_table)

    def _get_files(self) -> list[tuple[str, str, str, str]]:
        """Get list of audio files with stage.

        Returns:
            List of (path, filename, stage, added_time) tuples.
        """
        app = self.app
        db = app.db
        config = app.config

        # Get files from database
        db_files = {f.path: f for f in db.list_audio_files()}

        # Also scan filesystem for files not in DB
        result = []
        watch_dir = config.watch_dir

        if watch_dir.exists():
            for file in watch_dir.iterdir():
                if file.is_file() and file.suffix.lower().lstrip(".") in self.AUDIO_EXTENSIONS:
                    path_str = str(file)
                    if path_str in db_files:
                        f = db_files[path_str]
                        added = f.added_at.strftime("%Y-%m-%d %H:%M") if f.added_at else "-"
                        stage = "transcribed" if f.transcribed_at else "to transcribe"
                        result.append((path_str, f.filename, stage, added))
                        del db_files[path_str]
                    else:
                        result.append((path_str, file.name, "to transcribe", "-"))

        # Add any remaining DB files (that might have been moved)
        for f in db_files.values():
            if Path(f.path).exists():
                added = f.added_at.strftime("%Y-%m-%d %H:%M") if f.added_at else "-"
                stage = "transcribed" if f.transcribed_at else "to transcribe"
                result.append((f.path, f.filename, stage, added))

        return result

    def _refresh_table(self) -> None:
        """Refresh the file table."""
        table = self.query_one("#files-table", DataTable)
        table.clear()

        files = self._get_files()
        if not files:
            table.add_row("No audio files found", "-", "-")
            return

        for path, filename, stage, added in files:
            stage_icon = "+" if stage == "transcribed" else "o"
            table.add_row(filename, f"{stage_icon} {stage}", added, key=path)

    def _get_selected_path(self) -> str | None:
        """Get the currently selected file path."""
        table = self.query_one("#files-table", DataTable)
        if table.row_count == 0:
            return None

        cell_key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0))
        row_key = cell_key.row_key
        if row_key:
            return str(row_key.value)
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "transcribe-btn":
            self.action_transcribe_selected()
        elif button_id == "delete-btn":
            self.action_delete_selected()
        elif button_id == "refresh-btn":
            self.action_refresh()
        elif button_id == "open-btn":
            self.action_open_folder()
        elif button_id == "back-btn":
            self.action_go_back()

    def action_transcribe_selected(self) -> None:
        """Transcribe the selected file."""
        table = self.query_one("#files-table", DataTable)
        if table.row_count == 0:
            self.notify("No files to transcribe", severity="warning")
            return

        cell_key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0))
        row_key = cell_key.row_key
        if not row_key:
            return

        path = str(row_key.value)

        # Check if already transcribed
        if self.app.db.is_transcribed(path):
            self.notify("File already transcribed", severity="warning")
            return

        # Get API key
        api_key = self.app.config.get_api_key()
        if not api_key:
            self.notify("AssemblyAI API key not configured", severity="error")
            return

        self.notify(f"Starting transcription: {Path(path).name}")

        # Run transcription in background
        self.run_worker(
            self._transcribe_file(path, api_key),
            name="transcribe",
            description=f"Transcribing {Path(path).name}",
        )

    async def _transcribe_file(self, path: str, api_key: str) -> None:
        """Transcribe a file (runs in worker thread)."""
        try:
            transcriber = Transcriber(api_key)
            output_dir = self.app.config.raw_transcripts_dir

            def progress(msg: str) -> None:
                self.app.call_from_thread(self.notify, msg, severity="information")

            transcript_path = transcriber.transcribe_and_save(path, output_dir, progress)

            # Update database
            self.app.db.mark_transcribed(path, transcript_path)
            audio_id = self.app.db.get_audio_id(path)
            self.app.db.add_transcript(transcript_path, audio_id)

            self.app.call_from_thread(self.notify, f"Transcription complete: {transcript_path.name}")
            self.app.call_from_thread(self._refresh_table)

        except Exception as e:
            self.app.call_from_thread(self.notify, f"Transcription failed: {e}", severity="error")

    def action_delete_selected(self) -> None:
        """Delete the selected file."""
        table = self.query_one("#files-table", DataTable)
        if table.row_count == 0:
            self.notify("No files to delete", severity="warning")
            return

        cell_key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0))
        row_key = cell_key.row_key
        if not row_key:
            return

        path = Path(str(row_key.value))

        # Delete file and DB record
        if path.exists():
            path.unlink()
        self.app.db.delete_audio(str(path))

        self.notify(f"Deleted: {path.name}")
        self._refresh_table()

    def action_refresh(self) -> None:
        """Refresh the file list."""
        # Scan and add new files to database
        watch_dir = self.app.config.watch_dir
        if watch_dir.exists():
            for file in watch_dir.iterdir():
                if file.is_file() and file.suffix.lower().lstrip(".") in self.AUDIO_EXTENSIONS:
                    if not self.app.db.audio_exists(str(file)):
                        self.app.db.add_audio(str(file))

        self._refresh_table()
        self.notify("File list refreshed")

    def action_open_folder(self) -> None:
        """Open the watch directory in file manager."""
        import subprocess

        watch_dir = self.app.config.watch_dir
        if watch_dir.exists():
            subprocess.Popen(["xdg-open", str(watch_dir)])
            self.notify(f"Opening: {watch_dir}")
        else:
            self.notify("Watch directory does not exist", severity="warning")

    def action_go_back(self) -> None:
        """Go back to main menu."""
        self.app.pop_screen()
