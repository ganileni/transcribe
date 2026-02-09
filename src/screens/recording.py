"""Recording screen for Transcribe TUI."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static


class RecordingScreen(Screen):
    """Recording control screen with start/stop and live duration."""

    BINDINGS = [
        ("r", "toggle_recording", "Toggle Recording"),
        ("p", "toggle_pause", "Pause/Resume"),
        ("escape", "go_back", "Back"),
    ]

    is_recording = reactive(False)
    duration = reactive("00:00:00")

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="recording-container"):
            with Vertical(id="recording-box"):
                yield Label("Recording Controls", classes="title")
                yield Label("Status: Idle", id="rec-status")
                yield Label("00:00:00", id="rec-duration")
                with Horizontal(id="rec-buttons"):
                    yield Button("Start", id="start-btn", variant="success")
                    yield Button("Stop", id="stop-btn", variant="error", disabled=True)
                    yield Button("Pause", id="pause-btn", disabled=True)
                    yield Button("Back", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        self._update_display()
        self.set_interval(1.0, self._update_display)

    def _update_display(self) -> None:
        """Update the recording display."""
        app = self.app
        recorder = app.recorder

        status_label = self.query_one("#rec-status", Label)
        duration_label = self.query_one("#rec-duration", Label)
        recording_box = self.query_one("#recording-box")
        start_btn = self.query_one("#start-btn", Button)
        stop_btn = self.query_one("#stop-btn", Button)
        pause_btn = self.query_one("#pause-btn", Button)

        if recorder.is_recording:
            self.is_recording = True
            self.duration = recorder.get_duration()

            if recorder.is_paused:
                status_label.update("Status: PAUSED")
                status_label.add_class("recording")
                pause_btn.label = "Resume"
            else:
                status_label.update("Status: RECORDING")
                status_label.add_class("recording")
                pause_btn.label = "Pause"

            duration_label.update(self.duration)
            recording_box.add_class("recording")
            start_btn.disabled = True
            stop_btn.disabled = False
            pause_btn.disabled = False
        else:
            self.is_recording = False
            self.duration = "00:00:00"

            status_label.update("Status: Idle")
            status_label.remove_class("recording")
            duration_label.update("00:00:00")
            recording_box.remove_class("recording")
            start_btn.disabled = False
            stop_btn.disabled = True
            pause_btn.disabled = True
            pause_btn.label = "Pause"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "start-btn":
            self.action_start_recording()
        elif button_id == "stop-btn":
            self.action_stop_recording()
        elif button_id == "pause-btn":
            self.action_toggle_pause()
        elif button_id == "back-btn":
            self.action_go_back()

    def action_start_recording(self) -> None:
        """Start recording."""
        app = self.app
        try:
            file = app.recorder.start()
            self._update_display()
            self.notify(f"Recording started: {file.name}", severity="information")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_stop_recording(self) -> None:
        """Stop recording."""
        app = self.app
        try:
            file = app.recorder.stop()
            if file:
                app.db.add_audio(file)
                self.notify(f"Saved: {file.name}", severity="information")
            self._update_display()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_toggle_recording(self) -> None:
        """Toggle recording state."""
        if self.is_recording:
            self.action_stop_recording()
        else:
            self.action_start_recording()

    def action_toggle_pause(self) -> None:
        """Toggle pause/resume on the current recording."""
        recorder = self.app.recorder
        if not recorder.is_recording:
            return
        if recorder.is_paused:
            recorder.resume()
            self.notify("Recording resumed", severity="information")
        else:
            recorder.pause()
            self.notify("Recording paused", severity="information")
        self._update_display()

    def action_go_back(self) -> None:
        """Go back to main menu."""
        self.app.pop_screen()
