"""Main menu screen for Transcribe TUI."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static
from textual.worker import Worker, WorkerState

from ..core.transcriber import Transcriber, TranscriptionError


class MainMenuScreen(Screen):
    """Main menu screen with recording status and quick actions."""

    BINDINGS = [
        ("r", "toggle_recording", "Toggle Recording"),
        ("a", "toggle_auto_process", "Auto Process"),
        ("f", "show_files", "Files"),
        ("l", "show_labeling", "Label"),
        ("p", "process_all", "Process"),
        ("c", "edit_config", "Config"),
        ("q", "quit", "Quit"),
    ]

    is_recording = reactive(False)
    duration = reactive("00:00:00")
    pending_count = reactive(0)
    unlabeled_count = reactive(0)
    auto_process_enabled = reactive(False)

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with Vertical(id="recording-status"):
                yield Label("Recording", classes="section-title")
                with Horizontal():
                    yield Label("Status: Idle", id="status-label")
                    yield Label("Duration: 00:00:00", id="duration-label")
                with Horizontal(id="recording-buttons"):
                    yield Button("Start Recording", id="start-btn", variant="success")
                    yield Button("Stop Recording", id="stop-btn", variant="error", disabled=True)

            with Vertical(id="quick-actions"):
                yield Label("Quick Actions", classes="section-title")
                with Horizontal():
                    yield Button("\\[F]iles", id="files-btn", classes="action-button")
                    yield Button("\\[L]abel", id="label-btn", classes="action-button")
                    yield Button("\\[P]rocess", id="process-btn", classes="action-button")
                    yield Button("\\[C]onfig", id="config-btn", classes="action-button")
                    yield Button("\\[Q]uit", id="quit-btn", classes="action-button", variant="error")

            with Vertical(id="status-bar"):
                yield Label("Status", classes="section-title")
                with Horizontal():
                    yield Label("Pending: 0 files", id="pending-label")
                    yield Label("  |  ", classes="info-text")
                    yield Label("Unlabeled: 0 transcripts", id="unlabeled-label")
                    yield Label("  |  ", classes="info-text")
                    yield Label("Auto: OFF", id="auto-label")
                    yield Button("\\[A]uto", id="auto-btn", classes="action-button")
        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        self.auto_process_enabled = self.app.config.auto_process
        self._update_status()
        self._update_recording_status()
        self._update_auto_label()
        self.set_interval(1.0, self._update_recording_status)
        self.set_interval(5.0, self._scan_for_new_files)

    def _update_auto_label(self) -> None:
        """Update the auto-process label."""
        label = self.query_one("#auto-label", Label)
        status = "ON" if self.auto_process_enabled else "OFF"
        label.update(f"Auto: {status}")

    def _update_status(self) -> None:
        """Update status counts from database."""
        app = self.app
        self.pending_count = app.db.get_pending_count()
        self.unlabeled_count = app.db.get_unlabeled_count()

        self.query_one("#pending-label", Label).update(f"Pending: {self.pending_count} files")
        self.query_one("#unlabeled-label", Label).update(
            f"Unlabeled: {self.unlabeled_count} transcripts"
        )

    def _update_recording_status(self) -> None:
        """Update recording status display."""
        app = self.app
        recorder = app.recorder

        status_widget = self.query_one("#recording-status")
        status_label = self.query_one("#status-label", Label)
        duration_label = self.query_one("#duration-label", Label)
        start_btn = self.query_one("#start-btn", Button)
        stop_btn = self.query_one("#stop-btn", Button)

        if recorder.is_recording:
            self.is_recording = True
            self.duration = recorder.get_duration()

            status_widget.add_class("recording")
            status_label.update("Status: RECORDING")
            status_label.add_class("recording")
            duration_label.update(f"Duration: {self.duration}")
            start_btn.disabled = True
            stop_btn.disabled = False
        else:
            self.is_recording = False
            self.duration = "00:00:00"

            status_widget.remove_class("recording")
            status_label.update("Status: Idle")
            status_label.remove_class("recording")
            duration_label.update("Duration: 00:00:00")
            start_btn.disabled = False
            stop_btn.disabled = True

    def _scan_for_new_files(self) -> None:
        """Scan watch directory for new audio files."""
        app = self.app
        watch_dir = app.config.watch_dir

        if not watch_dir.exists():
            return

        audio_extensions = {"mp4", "m4a", "mp3", "wav", "ogg", "webm", "flac"}
        new_files = []

        for file in watch_dir.iterdir():
            if file.is_file() and file.suffix.lower().lstrip(".") in audio_extensions:
                if not app.db.audio_exists(str(file)):
                    app.db.add_audio(str(file))
                    new_files.append(file)

        if new_files:
            self._update_status()
            self.notify(f"Found {len(new_files)} new file(s)")

            # Auto-process if enabled
            if self.auto_process_enabled:
                self._auto_process_new_files()

    def _auto_process_new_files(self) -> None:
        """Auto-process pending files if configured."""
        app = self.app
        api_key = app.config.get_api_key()

        if not api_key:
            return  # Silent - no API key configured

        pending = app.db.get_pending_audio_files()
        if pending:
            self.run_worker(self._process_files(pending), name="auto_process", exclusive=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "start-btn":
            self.action_start_recording()
        elif button_id == "stop-btn":
            self.action_stop_recording()
        elif button_id == "files-btn":
            self.action_show_files()
        elif button_id == "label-btn":
            self.action_show_labeling()
        elif button_id == "process-btn":
            self.action_process_all()
        elif button_id == "config-btn":
            self.action_edit_config()
        elif button_id == "auto-btn":
            self.action_toggle_auto_process()
        elif button_id == "quit-btn":
            self.action_quit()

    def action_start_recording(self) -> None:
        """Start recording."""
        app = self.app
        try:
            app.recorder.start()
            self._update_recording_status()
            self.notify("Recording started", severity="information")
        except Exception as e:
            self.notify(f"Error starting recording: {e}", severity="error")

    def action_stop_recording(self) -> None:
        """Stop recording."""
        app = self.app
        try:
            file = app.recorder.stop()
            if file:
                app.db.add_audio(file)
                self._update_status()
                self.notify(f"Recording saved: {file.name}", severity="information")
            self._update_recording_status()
        except Exception as e:
            self.notify(f"Error stopping recording: {e}", severity="error")

    def action_toggle_recording(self) -> None:
        """Toggle recording state."""
        if self.is_recording:
            self.action_stop_recording()
        else:
            self.action_start_recording()

    def action_toggle_auto_process(self) -> None:
        """Toggle auto-processing of new files."""
        self.auto_process_enabled = not self.auto_process_enabled
        self._update_auto_label()
        status = "enabled" if self.auto_process_enabled else "disabled"
        self.notify(f"Auto-processing {status}")

    def action_show_files(self) -> None:
        """Show files screen."""
        self.app.action_show_files()

    def action_show_labeling(self) -> None:
        """Show labeling screen."""
        self.app.action_show_labeling()

    def action_process_all(self) -> None:
        """Process all pending recordings."""
        app = self.app
        pending = app.db.get_pending_audio_files()

        if not pending:
            self.notify("No pending files to process", severity="information")
            return

        self.notify(f"Processing {len(pending)} file(s)...", severity="information")
        self.run_worker(self._process_files(pending), name="process_files", exclusive=True)

    async def _process_files(self, files: list) -> None:
        """Background worker to process files."""
        app = self.app
        api_key = app.config.get_api_key()

        if not api_key:
            self.notify("No API key configured. Set assemblyai_api_key in config.", severity="error")
            return

        transcriber = Transcriber(api_key)
        output_dir = app.config.raw_transcripts_dir

        processed = 0
        for audio in files:
            try:
                self.notify(f"Transcribing: {audio.filename}", severity="information")

                # Transcribe and save
                transcript_path = transcriber.transcribe_and_save(
                    audio.path,
                    output_dir,
                    progress_callback=lambda msg: self.notify(msg),
                )

                # Update database
                audio_id = app.db.get_audio_id(audio.path)
                app.db.mark_transcribed(audio.path, str(transcript_path))
                if audio_id:
                    app.db.add_transcript(str(transcript_path), audio_id)

                processed += 1
                self.notify(f"Completed: {audio.filename}", severity="information")

            except TranscriptionError as e:
                self.notify(f"Error transcribing {audio.filename}: {e}", severity="error")
            except Exception as e:
                self.notify(f"Unexpected error: {e}", severity="error")

        self._update_status()
        self.notify(f"Processed {processed}/{len(files)} file(s)", severity="information")

    def action_edit_config(self) -> None:
        """Edit configuration."""
        import subprocess
        import os

        config_file = self.app.config.config_file
        editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vim"))

        self.app.suspend()
        subprocess.run([editor, str(config_file)])
        self.app.resume()

        # Reload config
        self.app.config._load()
        self.notify("Configuration reloaded")

    def action_quit(self) -> None:
        """Quit application."""
        self.app.exit()
