"""Main Textual application for Transcribe."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding

from .core import Config, Database, Recorder
from .screens import FilesScreen, LabelingScreen, MainMenuScreen, RecordingScreen, UnifiedScreen


class TranscribeApp(App):
    """Transcribe TUI application."""

    TITLE = "Transcribe"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("f", "show_files", "Files", show=True),
        Binding("l", "show_labeling", "Label", show=True),
        Binding("r", "show_recording", "Record", show=True),
        Binding("escape", "go_back", "Back", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.config.init()
        self.db = Database(self.config.db_file)
        self.db.init()
        self.recorder = Recorder(self.config.watch_dir)

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.push_screen(MainMenuScreen())

    def action_show_files(self) -> None:
        """Show unified files & labels screen."""
        self.push_screen(UnifiedScreen())

    def action_show_labeling(self) -> None:
        """Show unified files & labels screen."""
        self.push_screen(UnifiedScreen())

    def action_show_recording(self) -> None:
        """Show recording screen."""
        self.push_screen(RecordingScreen())

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        if len(self.screen_stack) > 1:
            self.pop_screen()


def main():
    """Entry point for the TUI application."""
    app = TranscribeApp()
    app.run()


if __name__ == "__main__":
    main()
