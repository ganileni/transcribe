"""Unified Files & Labels screen for Transcribe TUI."""

import functools
import re
from pathlib import Path
from threading import Timer

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from ..core import Summarizer
from ..models import TranscriptData


class UnifiedScreen(Screen):
    """Unified screen combining audio files and transcripts with all commands."""

    BINDINGS = [
        Binding("alt+t", "transcribe_selected", "Transcribe", priority=True),
        Binding("alt+d", "delete_selected", "Delete", priority=True),
        Binding("alt+r", "refresh", "Refresh", priority=True),
        Binding("alt+o", "open_folder", "Open Folder", priority=True),
        Binding("alt+n", "next_speaker", "Next Speaker", priority=True),
        Binding("alt+p", "prev_speaker", "Previous Speaker", priority=True),
        Binding("alt+m", "more_samples", "More Samples", priority=True),
        Binding("alt+s", "save_labels", "Save", priority=True),
        Binding("alt+g", "generate_summary", "Generate Summary", priority=True),
        Binding("alt+w", "regenerate_summary", "Regenerate Summary", priority=True),
        ("escape", "go_back", "Back"),
    ]

    AUDIO_EXTENSIONS = {"mp4", "m4a", "mp3", "wav", "ogg", "webm", "flac"}

    def __init__(self):
        super().__init__()
        self.items: list[dict] = []  # Combined list of audio files and transcripts
        self.current_transcript: TranscriptData | None = None
        self.current_transcript_path: Path | None = None
        self.current_speaker_index: int = 0
        self.sample_offset: int = 0
        self._delete_pending_path: str | None = None
        self._delete_timer: Timer | None = None

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
                yield Button("\\[Alt+T]ranscribe", id="transcribe-btn", variant="primary")
                yield Button("\\[Alt+D]elete", id="delete-btn", variant="error")
                yield Button("\\[Alt+R]efresh", id="refresh-btn")
                yield Button("\\[Alt+O]pen Folder", id="open-btn")
                yield Button("\\[Alt+P]revious", id="prev-btn")
                yield Button("\\[Alt+N]ext", id="next-btn")
                yield Button("\\[Alt+M]ore Samples", id="more-btn")
                yield Button("\\[Alt+S]ave", id="save-btn", variant="success")
                yield Button("\\[Alt+G]enerate Summary", id="summary-btn", variant="primary")
                yield Button("\\[Alt+W] Regenerate", id="regen-btn", variant="warning")
                yield Button("\\[Esc] Back", id="back-btn")
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
                dur_secs = item.get("duration_seconds")
                duration = self._format_duration(dur_secs) if dur_secs else "-"

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
            self.sample_offset = 0
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
        samples = self.current_transcript.get_speaker_samples(
            speaker.id, num_samples=3, offset=self.sample_offset
        )
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
        elif button_id == "regen-btn":
            self.action_regenerate_summary()
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
            functools.partial(self._transcribe_file, audio_path, api_key),
            name="transcribe",
            description=f"Transcribing {Path(audio_path).name}",
            thread=True,
        )

    def _transcribe_file(self, path: str, api_key: str) -> None:
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

    def _reset_delete_pending(self) -> None:
        """Reset the pending delete state."""
        self._delete_pending_path = None
        if self._delete_timer:
            self._delete_timer.cancel()
            self._delete_timer = None

    def action_delete_selected(self) -> None:
        """Delete the selected file (requires double-tap within 3 seconds)."""
        item = self._get_selected_item()
        if not item:
            self.notify("No item selected", severity="warning")
            return

        audio_path = item.get("audio_path")
        if not audio_path:
            return

        if self._delete_pending_path == audio_path:
            # Second press: execute delete
            self._reset_delete_pending()
            path = Path(audio_path)
            if path.exists():
                path.unlink()
            self.app.db.delete_audio(audio_path)
            self.notify(f"Deleted: {path.name}")
            self._refresh_table()
        else:
            # First press: arm deletion
            self._reset_delete_pending()
            self._delete_pending_path = audio_path
            self._delete_timer = Timer(
                3.0, lambda: self.app.call_from_thread(self._reset_delete_pending)
            )
            self._delete_timer.daemon = True
            self._delete_timer.start()
            self.notify(
                f"Press Alt+D again to confirm deletion of {Path(audio_path).name}",
                severity="warning",
                timeout=3,
            )

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
                    "All speakers labeled! Press [bold]Alt+S[/bold] to save or "
                    "[bold]Alt+G[/bold] to save & summarize"
                )

        self.sample_offset = 0
        self._show_current_speaker()

    def action_prev_speaker(self) -> None:
        """Move to previous speaker."""
        if not self.current_transcript:
            return

        self._save_current_speaker_name()
        self.current_speaker_index -= 1
        if self.current_speaker_index < 0:
            self.current_speaker_index = len(self.current_transcript.speakers) - 1
        self.sample_offset = 0
        self._show_current_speaker()

    def action_more_samples(self) -> None:
        """Show next page of sample utterances."""
        if not self.current_transcript:
            return

        self.sample_offset += 3
        self._show_current_speaker()

    def _build_speaker_rename_map(self) -> dict[str, str]:
        """Build a mapping of old speaker names to new names from current utterances.

        Compares the current utterance speaker values against the new names
        in the speakers list to find renames.
        """
        rename_map = {}
        # Collect current (old) speaker values from utterances
        old_speakers_in_utts = {utt.speaker for utt in self.current_transcript.utterances}
        # Map: speaker.id -> speaker.name (new)
        id_to_new = {s.id: s.name for s in self.current_transcript.speakers if s.name}
        # Map: old utterance speaker -> new name
        # If utterance speaker matches an ID, the new name is id_to_new[id]
        # If utterance speaker is an old name (already labeled), find which speaker
        # originally had that ID by checking if any speaker.id maps to a different name
        for speaker in self.current_transcript.speakers:
            if not speaker.name:
                continue
            # The utterance might use speaker.id (unlabeled) or an old name (relabeled)
            if speaker.id in old_speakers_in_utts and speaker.name != speaker.id:
                rename_map[speaker.id] = speaker.name
            # Check if old name is in utterances (relabeling case)
            for old_name in old_speakers_in_utts:
                if old_name == speaker.id:
                    continue
                # This old_name belongs to this speaker if it was their previous name
                # We detect this by checking: no other speaker has this as their id,
                # and this speaker's id is absent from utterances
                if (old_name not in id_to_new
                        and speaker.id not in old_speakers_in_utts
                        and old_name != speaker.name):
                    rename_map[old_name] = speaker.name
        return rename_map

    def _update_summary_file(self, rename_map: dict[str, str]) -> None:
        """Update speaker names in the summary file using regex replacement."""
        summary_path_str = self.app.db.get_summary_path(str(self.current_transcript_path))
        if not summary_path_str:
            return
        summary_path = Path(summary_path_str)
        if not summary_path.exists():
            return

        content = summary_path.read_text()
        for old_name, new_name in rename_map.items():
            content = re.sub(rf"\b{re.escape(old_name)}\b", new_name, content)
        summary_path.write_text(content)

    def action_save_labels(self) -> None:
        """Save all labels to the transcript file."""
        if not self.current_transcript or not self.current_transcript_path:
            self.notify("No transcript loaded", severity="warning")
            return

        self._save_current_speaker_name()

        # Build rename map before replacing speaker values
        rename_map = self._build_speaker_rename_map()

        # Check if all speakers are labeled
        all_labeled = all(s.name for s in self.current_transcript.speakers)

        # Replace speaker IDs/old names with new names in utterances
        self.current_transcript.replace_speaker_ids_with_names()
        # Also replace old names with new names for relabeling
        for old_name, new_name in rename_map.items():
            for utt in self.current_transcript.utterances:
                if utt.speaker == old_name:
                    utt.speaker = new_name

        if all_labeled:
            self.current_transcript.mark_labeled()
            speaker_names = ", ".join(self.current_transcript.get_participants())
            self.app.db.mark_labeled(str(self.current_transcript_path), speaker_names)

        # Save to file
        self.current_transcript.save(self.current_transcript_path)

        # Update summary file if speaker names changed
        if rename_map:
            self._update_summary_file(rename_map)
            self.notify("Labels and summary updated", severity="information")
        else:
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
            functools.partial(self._generate_summary, auto_title),
            name="summarize",
            description=f"Summarizing {self.current_transcript_path.name}",
            thread=True,
        )

    def _generate_summary(self, title: str) -> None:
        """Generate summary (runs in worker thread)."""
        try:
            summarizer = Summarizer()
            output_dir = self.app.config.summaries_dir

            def progress(msg: str) -> None:
                self.app.call_from_thread(self.notify, msg, severity="information")

            summary_path, generated_title = summarizer.summarize_and_save(
                self.current_transcript_path,
                title,
                output_dir,
                progress,
            )

            self.app.db.mark_summarized(
                str(self.current_transcript_path), str(summary_path)
            )
            self.app.db.update_meeting_title(
                str(self.current_transcript_path), generated_title
            )

            self.app.call_from_thread(
                self.notify, f"Summary saved: {summary_path.name}", severity="information"
            )
            self.app.call_from_thread(self._refresh_table)

        except Exception as e:
            self.app.call_from_thread(
                self.notify, f"Summary failed: {e}", severity="error"
            )
        finally:
            def _restore_btn():
                summary_btn = self.query_one("#summary-btn", Button)
                summary_btn.disabled = False
                summary_btn.label = "\\[Alt+G]enerate Summary"
            self.app.call_from_thread(_restore_btn)

    def action_regenerate_summary(self) -> None:
        """Regenerate summary for a transcript that already has one."""
        if not self.current_transcript or not self.current_transcript_path:
            self.notify("No transcript loaded", severity="warning")
            return

        if not self.current_transcript.labeled:
            self.notify("Please label all speakers first", severity="warning")
            return

        summary_path = self.app.db.get_summary_path(str(self.current_transcript_path))
        if not summary_path:
            self.notify("No existing summary to regenerate. Use Alt+G to generate.", severity="warning")
            return

        # Delete old summary file
        old_summary = Path(summary_path)
        if old_summary.exists():
            old_summary.unlink()

        # Generate title from filename
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", self.current_transcript_path.name)
        date = date_match.group(1) if date_match else ""
        participants = "-".join(self.current_transcript.get_participants())
        auto_title = f"{date} {participants}".strip() or "Meeting"

        regen_btn = self.query_one("#regen-btn", Button)
        regen_btn.disabled = True
        regen_btn.label = "Regenerating..."

        self.notify(
            "Regenerating summary... this may take a minute",
            severity="information",
            timeout=10,
        )

        self.run_worker(
            functools.partial(self._regenerate_summary, auto_title),
            name="regenerate",
            description=f"Regenerating summary for {self.current_transcript_path.name}",
            thread=True,
        )

    def _regenerate_summary(self, title: str) -> None:
        """Regenerate summary (runs in worker thread)."""
        try:
            summarizer = Summarizer()
            output_dir = self.app.config.summaries_dir

            def progress(msg: str) -> None:
                self.app.call_from_thread(self.notify, msg, severity="information")

            summary_path, generated_title = summarizer.summarize_and_save(
                self.current_transcript_path,
                title,
                output_dir,
                progress,
            )

            self.app.db.mark_summarized(
                str(self.current_transcript_path), str(summary_path)
            )
            self.app.db.update_meeting_title(
                str(self.current_transcript_path), generated_title
            )

            self.app.call_from_thread(
                self.notify, f"Summary regenerated: {summary_path.name}", severity="information"
            )
            self.app.call_from_thread(self._refresh_table)

        except Exception as e:
            self.app.call_from_thread(
                self.notify, f"Regeneration failed: {e}", severity="error"
            )
        finally:
            def _restore_btn():
                regen_btn = self.query_one("#regen-btn", Button)
                regen_btn.disabled = False
                regen_btn.label = "\\[Alt+W] Regenerate"
            self.app.call_from_thread(_restore_btn)

    def action_refresh(self) -> None:
        """Refresh the file and transcript list."""
        self._refresh_table()
        self.notify(f"Found {len(self.items)} item(s)")

    def action_go_back(self) -> None:
        """Go back to main menu."""
        self.app.pop_screen()
