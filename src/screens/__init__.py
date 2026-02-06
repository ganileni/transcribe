"""TUI screens for the Transcribe application."""

from .main_menu import MainMenuScreen
from .recording import RecordingScreen
from .files import FilesScreen
from .labeling import LabelingScreen
from .unified import UnifiedScreen

__all__ = [
    "MainMenuScreen",
    "RecordingScreen",
    "FilesScreen",
    "LabelingScreen",
    "UnifiedScreen",
]
