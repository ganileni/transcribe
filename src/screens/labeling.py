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
        ("r", "refresh", "Refresh"),
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
        with Container(id="labeling-container"):
            yield Label("Transcripts", classes="title")
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
                yield Button("\\[R]efresh", id="refresh-btn")
                yield Button("\\[P]revious", id="prev-btn")
                yield Button("\\[N]ext", id="next-btn")
                yield Button("\\[M]ore Samples", id="more-btn")
                yield Button("\\[S]ave All", id="save-btn", variant="success")
                yield Button("\\[G]enerate Summary", id="summary-btn", variant="primary")
                yield Button("\\[B]ack", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        table = self.query_one("#transcript-list", DataTable)
        table.add_columns("Name", "Filename", "Stage", "Date", "Duration", "Speakers")
        table.cursor_type = "row"
        self._refresh_transcripts()
        self.set_interval(60.0, self._refresh_transcripts)

    def _refresh_transcripts(self) -> None:
        """Refresh the transcript list."""
        try:
            table = self.query_one("#transcript-list", DataTable)
            table.clear()

            # Get all transcripts from DB, sorted by most recent activity
            all_transcripts = self.app.db.list_all_transcripts()
            self.transcripts = []

            for t in all_transcripts:
                path = Path(t.path)
                if path.exists():
                    self.transcripts.append(path)
                    try:
                        transcript = TranscriptData.load(path)
                        date = transcript.transcribed.strftime("%Y-%m-%d %H:%M")
                        duration = self._format_duration(transcript.duration_seconds)
                        # For unlabeled, show count + IDs; for labeled, show names from DB
                        if t.speakers:
                            speakers_display = t.speakers
                        else:
                            num_speakers = len(transcript.speakers)
                            speaker_ids = [s.id for s in transcript.speakers]
                            speakers_display = f"{num_speakers} ({', '.join(speaker_ids)})"
                    except Exception:
                        date = "-"
                        duration = "-"
                        speakers_display = t.speakers if t.speakers else "?"
                    # Get stage from DB record status property
                    stage = t.status  # "unlabeled", "labeled", or "summarized"
                    # Name column: show meeting_title if set, else filename
                    name = t.meeting_title if t.meeting_title else path.name
                    table.add_row(
                        name, path.name, stage, date, duration, speakers_display, key=t.path
                    )

            if not self.transcripts:
                table.add_row("No transcripts", "-", "-", "-", "-", "-")
        except Exception as e:
            self.notify(f"Error refreshing: {e}", severity="error")

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

        if button_id == "refresh-btn":
            self.action_refresh()
        elif button_id == "prev-btn":
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

        # Check if we've gone through all speakers
        if self.current_speaker_index >= len(self.current_transcript.speakers):
            self.current_speaker_index = 0
            # Check if all speakers are now labeled
            if self._all_speakers_labeled():
                self.notify("All speakers labeled! Press [bold]S[/bold] to save or [bold]G[/bold] to save & summarize")

        self.sample_count = 3
        self._show_current_speaker()

    def _all_speakers_labeled(self) -> bool:
        """Check if all speakers have names assigned."""
        if not self.current_transcript:
            return False
        return all(s.name for s in self.current_transcript.speakers)

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
            # Get comma-separated speaker names
            speaker_names = ", ".join(self.current_transcript.get_participants())
            self.app.db.mark_labeled(str(self.current_transcript_path), speaker_names)

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
            self.app.db.mark_summarized(str(self.current_transcript_path), str(summary_path))
            self.app.db.update_meeting_title(str(self.current_transcript_path), generated_title)

            self.notify(f"Summary saved: {summary_path.name}", severity="information")
            self._refresh_transcripts()

        except Exception as e:
            self.notify(f"Summary failed: {e}", severity="error")
        finally:
            # Re-enable button
            summary_btn = self.query_one("#summary-btn", Button)
            summary_btn.disabled = False
            summary_btn.label = "\\[G]enerate Summary"

    def action_refresh(self) -> None:
        """Refresh the transcript list."""
        self._refresh_transcripts()
        self.notify(f"Found {len(self.transcripts)} transcript(s)")

    def action_go_back(self) -> None:
        """Go back to main menu."""
        self.app.pop_screen()
