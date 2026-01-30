"""Labeling screen for Transcribe TUI."""

import re
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from ..core import Summarizer
from ..models import TranscriptData


class LabelingScreen(Screen):
    """Speaker labeling screen."""

    BINDINGS = [
        ("n", "next_speaker", "Next Speaker"),
        ("p", "prev_speaker", "Previous Speaker"),
        ("m", "more_samples", "More Samples"),
        ("s", "save_labels", "Save"),
        ("g", "generate_summary", "Generate Summary"),
        ("escape", "go_back", "Back"),
    ]

    def __init__(self):
        super().__init__()
        self.transcripts: list[Path] = []
        self.current_transcript: TranscriptData | None = None
        self.current_transcript_path: Path | None = None
        self.current_speaker_index: int = 0
        self.sample_count: int = 3

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="labeling-container"):
            yield Label("Unlabeled Transcripts", classes="title")
            yield DataTable(id="transcript-list")

            with Vertical(id="speaker-form"):
                yield Label("Speaker Labeling", classes="section-title")
                yield Label("Select a transcript above", id="transcript-name")
                yield Label("", id="speaker-id")
                with VerticalScroll(id="samples-list"):
                    yield Static("", id="samples-content")
                yield Label("Name:")
                yield Input(placeholder="Enter speaker name", id="speaker-input")

            with Horizontal(id="labeling-actions"):
                yield Button("[P]revious", id="prev-btn")
                yield Button("[N]ext", id="next-btn")
                yield Button("[M]ore Samples", id="more-btn")
                yield Button("[S]ave All", id="save-btn", variant="success")
                yield Button("[G]enerate Summary", id="summary-btn", variant="primary")
                yield Button("[B]ack", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        table = self.query_one("#transcript-list", DataTable)
        table.add_columns("Transcript", "Speakers", "Status")
        table.cursor_type = "row"
        self._refresh_transcripts()

    def _refresh_transcripts(self) -> None:
        """Refresh the transcript list."""
        table = self.query_one("#transcript-list", DataTable)
        table.clear()

        # Get unlabeled transcripts from DB
        unlabeled = self.app.db.get_unlabeled()
        self.transcripts = []

        # Also scan filesystem
        raw_dir = self.app.config.raw_transcripts_dir
        if raw_dir.exists():
            for file in raw_dir.glob("*.yaml"):
                path_str = str(file)
                if path_str not in unlabeled:
                    # Check if it's unlabeled
                    try:
                        content = file.read_text()
                        if "labeled: false" in content:
                            unlabeled.append(path_str)
                    except Exception:
                        pass

        for path_str in unlabeled:
            path = Path(path_str)
            if path.exists():
                self.transcripts.append(path)
                try:
                    transcript = TranscriptData.load(path)
                    num_speakers = len(transcript.speakers)
                    status = "labeled" if transcript.labeled else "unlabeled"
                except Exception:
                    num_speakers = "?"
                    status = "error"
                table.add_row(path.name, f"{num_speakers} speakers", status, key=path_str)

        if not self.transcripts:
            table.add_row("No unlabeled transcripts", "-", "-")

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
                # Truncate long samples
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle transcript selection."""
        if event.row_key and event.row_key.value:
            path = Path(str(event.row_key.value))
            if path.exists():
                self._load_transcript(path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "prev-btn":
            self.action_prev_speaker()
        elif button_id == "next-btn":
            self.action_next_speaker()
        elif button_id == "save-btn":
            self.action_save_labels()
        elif button_id == "more-btn":
            self.action_more_samples()
        elif button_id == "summary-btn":
            self.action_generate_summary()
        elif button_id == "back-btn":
            self.action_go_back()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle enter in input field - move to next speaker."""
        self._save_current_speaker_name()
        self.action_next_speaker()

    def action_next_speaker(self) -> None:
        """Move to next speaker."""
        if not self.current_transcript:
            return

        self._save_current_speaker_name()
        self.current_speaker_index += 1
        if self.current_speaker_index >= len(self.current_transcript.speakers):
            self.current_speaker_index = 0
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
            self.app.db.mark_labeled(str(self.current_transcript_path))

        # Save to file
        self.current_transcript.save(self.current_transcript_path)

        self.notify("Labels saved", severity="information")
        self._refresh_transcripts()

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

        # For now, use auto-generated title
        # TODO: Add input dialog for custom title
        self.notify(f"Generating summary: {auto_title}")

        self.run_worker(
            self._generate_summary(auto_title),
            name="summarize",
            description=f"Summarizing {self.current_transcript_path.name}",
        )

    async def _generate_summary(self, title: str) -> None:
        """Generate summary (runs in worker thread)."""
        try:
            summarizer = Summarizer()
            output_dir = self.app.config.summaries_dir

            def progress(msg: str) -> None:
                self.app.call_from_thread(self.notify, msg, severity="information")

            summary_path = summarizer.summarize_and_save(
                self.current_transcript_path,
                title,
                output_dir,
                progress,
            )

            # Update database
            self.app.db.mark_summarized(str(self.current_transcript_path), str(summary_path))

            self.app.call_from_thread(
                self.notify, f"Summary saved: {summary_path.name}", severity="information"
            )

        except Exception as e:
            self.app.call_from_thread(self.notify, f"Summary failed: {e}", severity="error")

    def action_go_back(self) -> None:
        """Go back to main menu."""
        self.app.pop_screen()
