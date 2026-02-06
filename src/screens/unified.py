"""Unified Files & Labels screen for Transcribe TUI."""

import re
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from ..core import Summarizer
from ..models import TranscriptData


class UnifiedScreen(Screen):
    """Unified screen combining audio files and transcripts with all commands."""

    BINDINGS = [
        ("t", "transcribe_selected", "Transcribe"),
        ("d", "delete_selected", "Delete"),
        ("r", "refresh", "Refresh"),
        ("o", "open_folder", "Open Folder"),
        ("n", "next_speaker", "Next Speaker"),
        ("p", "prev_speaker", "Previous Speaker"),
        ("m", "more_samples", "More Samples"),
        ("s", "save_labels", "Save"),
        ("g", "generate_summary", "Generate Summary"),
        ("escape", "go_back", "Back"),
    ]

    AUDIO_EXTENSIONS = {"mp4", "m4a", "mp3", "wav", "ogg", "webm", "flac"}

    def __init__(self):
        super().__init__()
        self.items: list[dict] = []  # Combined list of audio files and transcripts
        self.current_transcript: TranscriptData | None = None
        self.current_transcript_path: Path | None = None
        self.current_speaker_index: int = 0
        self.sample_count: int = 3

    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to MM:SS or HH:MM:SS."""
        if seconds < 3600:
            return f"{seconds // 60}:{seconds % 60:02d}"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="unified-container"):
            yield Label("Files & Transcripts", classes="title")
            yield DataTable(id="unified-table")

            with Vertical(id="speaker-form"):
                yield Label("Speaker Labeling", classes="section-title")
                yield Label("Select a transcript to label", id="transcript-name")
                yield Label("", id="speaker-id")
                with VerticalScroll(id="samples-list"):
                    yield Static("", id="samples-content")
                yield Label("Name:")
                yield Input(placeholder="Enter speaker name", id="speaker-input")

            with Horizontal(id="unified-actions"):
                yield Button("\\[T]ranscribe", id="transcribe-btn", variant="primary")
                yield Button("\\[D]elete", id="delete-btn", variant="error")
                yield Button("\\[R]efresh", id="refresh-btn")
                yield Button("\\[O]pen Folder", id="open-btn")
                yield Button("\\[P]revious", id="prev-btn")
                yield Button("\\[N]ext", id="next-btn")
                yield Button("\\[M]ore Samples", id="more-btn")
                yield Button("\\[S]ave", id="save-btn", variant="success")
                yield Button("\\[G]enerate Summary", id="summary-btn", variant="primary")
                yield Button("\\[B]ack", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        table = self.query_one("#unified-table", DataTable)
        table.add_columns("Name", "Filename", "Stage", "Speakers", "Date", "Duration")
        table.cursor_type = "row"
        self._refresh_table()
        self.set_interval(60.0, self._refresh_table)

    def _refresh_table(self) -> None:
        """Refresh the combined table with audio files and transcripts."""
        try:
            table = self.query_one("#unified-table", DataTable)
            table.clear()

            # Get unified list from database
            self.items = self.app.db.list_unified()

            # Also scan filesystem for new audio files not in DB
            watch_dir = self.app.config.watch_dir
            if watch_dir.exists():
                db_audio_paths = {
                    item["audio_path"]
                    for item in self.items
                    if item.get("audio_path")
                }
                for file in watch_dir.iterdir():
                    if (
                        file.is_file()
                        and file.suffix.lower().lstrip(".") in self.AUDIO_EXTENSIONS
                        and str(file) not in db_audio_paths
                    ):
                        # Add to database and items list
                        self.app.db.add_audio(str(file))
                        self.items.append({
                            "type": "audio",
                            "audio_path": str(file),
                            "audio_filename": file.name,
                            "stage": "to transcribe",
                            "speakers": None,
                            "date": None,
                            "duration": None,
                            "name": file.name,
                            "transcript_path": None,
                        })

            if not self.items:
                table.add_row("No files or transcripts", "-", "-", "-", "-", "-")
                return

            for item in self.items:
                name = item.get("name") or item.get("audio_filename") or "-"
                filename = item.get("audio_filename") or (
                    Path(item["transcript_path"]).name if item.get("transcript_path") else "-"
                )
                stage = item.get("stage", "-")
                speakers = item.get("speakers") or "-"
                date = item.get("date") or "-"
                duration = item.get("duration") or "-"

                # Create a unique key
                key = item.get("transcript_path") or item.get("audio_path") or filename

                table.add_row(name, filename, stage, speakers, date, duration, key=key)

        except Exception as e:
            self.notify(f"Error refreshing: {e}", severity="error")

    def _get_selected_item(self) -> dict | None:
        """Get the currently selected item."""
        table = self.query_one("#unified-table", DataTable)
        if table.row_count == 0:
            return None

        cell_key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0))
        row_key = cell_key.row_key
        if not row_key:
            return None

        key = str(row_key.value)
        for item in self.items:
            item_key = item.get("transcript_path") or item.get("audio_path")
            if item_key == key:
                return item
        return None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        item = self._get_selected_item()
        if not item:
            return

        # If it's a transcript, load it for labeling
        transcript_path = item.get("transcript_path")
        if transcript_path and Path(transcript_path).exists():
            self._load_transcript(Path(transcript_path))
        else:
            # Clear transcript form
            self.current_transcript = None
            self.current_transcript_path = None
            name_label = self.query_one("#transcript-name", Label)
            name_label.update("Select a transcript to label")
            speaker_label = self.query_one("#speaker-id", Label)
            speaker_label.update("")
            samples_content = self.query_one("#samples-content", Static)
            samples_content.update("")

    def _load_transcript(self, path: Path) -> None:
        """Load a transcript for labeling."""
        try:
            self.current_transcript = TranscriptData.load(path)
            self.current_transcript_path = path
            self.current_speaker_index = 0
            self.sample_count = 3
            self._show_current_speaker()

            name_label = self.query_one("#transcript-name", Label)
            name_label.update(f"Transcript: {path.name}")
        except Exception as e:
            self.notify(f"Error loading transcript: {e}", severity="error")

    def _show_current_speaker(self) -> None:
        """Display the current speaker for labeling."""
        if not self.current_transcript:
            return

        if self.current_speaker_index >= len(self.current_transcript.speakers):
            self.current_speaker_index = 0

        speaker = self.current_transcript.speakers[self.current_speaker_index]

        # Update speaker ID display
        speaker_label = self.query_one("#speaker-id", Label)
        total = len(self.current_transcript.speakers)
        speaker_label.update(
            f"Speaker {self.current_speaker_index + 1} of {total}: {speaker.id}"
        )

        # Get and display samples
        samples = self.current_transcript.get_speaker_samples(speaker.id, self.sample_count)
        samples_content = self.query_one("#samples-content", Static)

        if samples:
            sample_text = "Sample utterances:\n"
            for s in samples:
                if len(s) > 80:
                    s = s[:77] + "..."
                sample_text += f"  * \"{s}\"\n"
            samples_content.update(sample_text)
        else:
            samples_content.update("No sample utterances available")

        # Update input with current name
        name_input = self.query_one("#speaker-input", Input)
        name_input.value = speaker.name or ""
        name_input.focus()

    def _save_current_speaker_name(self) -> None:
        """Save the current speaker name from input."""
        if not self.current_transcript:
            return

        name_input = self.query_one("#speaker-input", Input)
        name = name_input.value.strip()

        if name:
            speaker = self.current_transcript.speakers[self.current_speaker_index]
            self.current_transcript.set_speaker_name(speaker.id, name)

    def _all_speakers_labeled(self) -> bool:
        """Check if all speakers have names assigned."""
        if not self.current_transcript:
            return False
        return all(s.name for s in self.current_transcript.speakers)

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
        elif button_id == "prev-btn":
            self.action_prev_speaker()
        elif button_id == "next-btn":
            self.action_next_speaker()
        elif button_id == "more-btn":
            self.action_more_samples()
        elif button_id == "save-btn":
            self.action_save_labels()
        elif button_id == "summary-btn":
            self.action_generate_summary()
        elif button_id == "back-btn":
            self.action_go_back()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle enter in input field - move to next speaker."""
        self._save_current_speaker_name()
        self.action_next_speaker()

    # Audio file actions

    def action_transcribe_selected(self) -> None:
        """Transcribe the selected audio file."""
        item = self._get_selected_item()
        if not item:
            self.notify("No item selected", severity="warning")
            return

        audio_path = item.get("audio_path")
        if not audio_path:
            self.notify("Select an audio file to transcribe", severity="warning")
            return

        if item.get("stage") not in ("to transcribe", "pending"):
            self.notify("File already transcribed", severity="warning")
            return

        # Get API key
        api_key = self.app.config.get_api_key()
        if not api_key:
            self.notify("AssemblyAI API key not configured", severity="error")
            return

        self.notify(f"Starting transcription: {Path(audio_path).name}")

        from ..core import Transcriber

        self.run_worker(
            self._transcribe_file(audio_path, api_key),
            name="transcribe",
            description=f"Transcribing {Path(audio_path).name}",
        )

    async def _transcribe_file(self, path: str, api_key: str) -> None:
        """Transcribe a file (runs in worker thread)."""
        from ..core import Transcriber

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

            self.app.call_from_thread(
                self.notify, f"Transcription complete: {transcript_path.name}"
            )
            self.app.call_from_thread(self._refresh_table)

        except Exception as e:
            self.app.call_from_thread(
                self.notify, f"Transcription failed: {e}", severity="error"
            )

    def action_delete_selected(self) -> None:
        """Delete the selected file."""
        item = self._get_selected_item()
        if not item:
            self.notify("No item selected", severity="warning")
            return

        audio_path = item.get("audio_path")
        if audio_path:
            path = Path(audio_path)
            if path.exists():
                path.unlink()
            self.app.db.delete_audio(audio_path)
            self.notify(f"Deleted: {path.name}")
            self._refresh_table()

    def action_open_folder(self) -> None:
        """Open the watch directory in file manager."""
        import subprocess

        watch_dir = self.app.config.watch_dir
        if watch_dir.exists():
            subprocess.Popen(["xdg-open", str(watch_dir)])
            self.notify(f"Opening: {watch_dir}")
        else:
            self.notify("Watch directory does not exist", severity="warning")

    # Speaker labeling actions

    def action_next_speaker(self) -> None:
        """Move to next speaker."""
        if not self.current_transcript:
            return

        self._save_current_speaker_name()
        self.current_speaker_index += 1

        if self.current_speaker_index >= len(self.current_transcript.speakers):
            self.current_speaker_index = 0
            if self._all_speakers_labeled():
                self.notify(
                    "All speakers labeled! Press [bold]S[/bold] to save or "
                    "[bold]G[/bold] to save & summarize"
                )

        self.sample_count = 3
        self._show_current_speaker()

    def action_prev_speaker(self) -> None:
        """Move to previous speaker."""
        if not self.current_transcript:
            return

        self._save_current_speaker_name()
        self.current_speaker_index -= 1
        if self.current_speaker_index < 0:
            self.current_speaker_index = len(self.current_transcript.speakers) - 1
        self.sample_count = 3
        self._show_current_speaker()

    def action_more_samples(self) -> None:
        """Show more sample utterances."""
        if not self.current_transcript:
            return

        self.sample_count += 3
        self._show_current_speaker()

    def action_save_labels(self) -> None:
        """Save all labels to the transcript file."""
        if not self.current_transcript or not self.current_transcript_path:
            self.notify("No transcript loaded", severity="warning")
            return

        self._save_current_speaker_name()

        # Check if all speakers are labeled
        all_labeled = all(s.name for s in self.current_transcript.speakers)

        # Replace speaker IDs with names in utterances
        self.current_transcript.replace_speaker_ids_with_names()

        if all_labeled:
            self.current_transcript.mark_labeled()
            speaker_names = ", ".join(self.current_transcript.get_participants())
            self.app.db.mark_labeled(str(self.current_transcript_path), speaker_names)

        # Save to file
        self.current_transcript.save(self.current_transcript_path)

        self.notify("Labels saved", severity="information")
        self._refresh_table()

    def action_generate_summary(self) -> None:
        """Generate summary for the current transcript."""
        if not self.current_transcript or not self.current_transcript_path:
            self.notify("No transcript loaded", severity="warning")
            return

        if not self.current_transcript.labeled:
            self.notify("Please label all speakers first", severity="warning")
            return

        # Generate title from filename
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", self.current_transcript_path.name)
        date = date_match.group(1) if date_match else ""
        participants = "-".join(self.current_transcript.get_participants())
        auto_title = f"{date} {participants}".strip() or "Meeting"

        # Disable button and show prominent notification
        summary_btn = self.query_one("#summary-btn", Button)
        summary_btn.disabled = True
        summary_btn.label = "Generating..."

        self.notify(
            "Generating summary... this may take a minute",
            severity="information",
            timeout=10,
        )

        self.run_worker(
            self._generate_summary(auto_title),
            name="summarize",
            description=f"Summarizing {self.current_transcript_path.name}",
        )

    async def _generate_summary(self, title: str) -> None:
        """Generate summary (runs in async worker)."""
        try:
            summarizer = Summarizer()
            output_dir = self.app.config.summaries_dir

            def progress(msg: str) -> None:
                self.notify(msg, severity="information")

            summary_path, generated_title = summarizer.summarize_and_save(
                self.current_transcript_path,
                title,
                output_dir,
                progress,
            )

            # Update database
            self.app.db.mark_summarized(
                str(self.current_transcript_path), str(summary_path)
            )
            self.app.db.update_meeting_title(
                str(self.current_transcript_path), generated_title
            )

            self.notify(f"Summary saved: {summary_path.name}", severity="information")
            self._refresh_table()

        except Exception as e:
            self.notify(f"Summary failed: {e}", severity="error")
        finally:
            # Re-enable button
            summary_btn = self.query_one("#summary-btn", Button)
            summary_btn.disabled = False
            summary_btn.label = "\\[G]enerate Summary"

    def action_refresh(self) -> None:
        """Refresh the file and transcript list."""
        self._refresh_table()
        self.notify(f"Found {len(self.items)} item(s)")

    def action_go_back(self) -> None:
        """Go back to main menu."""
        self.app.pop_screen()
