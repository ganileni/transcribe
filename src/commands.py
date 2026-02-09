"""Command palette provider for Transcribe TUI."""

from textual.command import DiscoveryHit, Hit, Hits, Provider

from .screens.main_menu import MainMenuScreen
from .screens.unified import UnifiedScreen


class TranscribeCommands(Provider):
    """Exposes Transcribe actions in the Ctrl+P command palette."""

    COMMANDS = [
        ("Files & Labels", "action_show_files", "Open files and speaker labeling screen"),
        ("Recording", "action_show_recording", "Open recording controls"),
        ("Edit Configuration", "action_edit_config", "Open config in $EDITOR"),
        ("Toggle Auto-Process", "action_toggle_auto_process", "Toggle auto-processing of new files"),
        ("Process All Pending", "action_process_all", "Transcribe all pending audio files"),
        ("Refresh Files", "action_refresh", "Rescan watch directory"),
        ("Transcribe Selected", "action_transcribe_selected", "Transcribe selected audio file"),
        ("Generate Summary", "action_generate_summary", "Generate summary for transcript"),
        ("Regenerate Summary", "action_regenerate_summary", "Regenerate existing summary"),
        ("Save Labels", "action_save_labels", "Save speaker labels"),
        ("Open Watch Folder", "action_open_folder", "Open recordings directory"),
        ("Quit", "action_quit", "Exit Transcribe"),
    ]

    # Commands that only make sense on UnifiedScreen
    UNIFIED_ONLY = {
        "action_refresh",
        "action_transcribe_selected",
        "action_generate_summary",
        "action_regenerate_summary",
        "action_save_labels",
        "action_open_folder",
    }

    # Commands that only make sense on MainMenuScreen
    MAIN_MENU_ONLY = {
        "action_toggle_auto_process",
        "action_process_all",
        "action_edit_config",
    }

    def _make_callback(self, action: str):
        """Build a callback that dispatches the given action."""
        async def callback() -> None:
            screen = self.app.screen
            if action in self.UNIFIED_ONLY:
                if isinstance(screen, UnifiedScreen):
                    getattr(screen, action)()
                else:
                    self.app.action_show_files()
            elif action in self.MAIN_MENU_ONLY:
                if isinstance(screen, MainMenuScreen):
                    getattr(screen, action)()
            elif action == "action_show_files":
                self.app.action_show_files()
            elif action == "action_show_recording":
                self.app.action_show_recording()
            elif action == "action_quit":
                self.app.exit()
        return callback

    async def discover(self) -> Hits:
        """Yield all commands for display before any user input."""
        for display, action, help_text in self.COMMANDS:
            yield DiscoveryHit(
                display=display,
                command=self._make_callback(action),
                help=help_text,
            )

    async def search(self, query: str) -> Hits:
        """Fuzzy-match commands against user input."""
        matcher = self.matcher(query)
        for display, action, help_text in self.COMMANDS:
            score = matcher.match(display)
            if score > 0:
                yield Hit(
                    score=score,
                    match_display=matcher.highlight(display),
                    command=self._make_callback(action),
                    help=help_text,
                )
