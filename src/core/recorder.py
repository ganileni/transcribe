"""Audio recording control using ffmpeg."""

import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable


class RecordingError(Exception):
    """Error during recording."""

    pass


class Recorder:
    """Audio recorder using ffmpeg with PulseAudio."""

    # State files
    STATE_DIR = Path("/tmp")
    STATE_FILE = STATE_DIR / "transcribe-recording-state"
    PID_FILE = STATE_DIR / "transcribe-recording-pid"
    FILE_FILE = STATE_DIR / "transcribe-recording-file"
    START_FILE = STATE_DIR / "transcribe-recording-start"
    PAUSE_FILE = STATE_DIR / "transcribe-recording-paused"
    PAUSED_AT_FILE = STATE_DIR / "transcribe-recording-paused-at"
    PAUSED_TOTAL_FILE = STATE_DIR / "transcribe-recording-paused-total"

    def __init__(self, output_dir: str | Path):
        """Initialize the recorder.

        Args:
            output_dir: Directory to save recordings.
        """
        self.output_dir = Path(output_dir)
        self._process: subprocess.Popen | None = None

    def _detect_audio_sources(self) -> tuple[str, str | None]:
        """Detect available audio sources.

        Returns:
            Tuple of (mic_source, system_source or None).
        """
        mic_source = "default"
        sys_source = None

        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "monitor" in line.lower():
                        sys_source = line.split()[1]
                        break
        except FileNotFoundError:
            pass

        return mic_source, sys_source

    @property
    def is_recording(self) -> bool:
        """Check if recording is in progress."""
        return self.STATE_FILE.exists()

    @property
    def is_paused(self) -> bool:
        """Check if recording is paused."""
        return self.PAUSE_FILE.exists()

    def _get_paused_total(self) -> int:
        """Get total seconds spent paused (accumulated + current pause if active)."""
        total = 0
        if self.PAUSED_TOTAL_FILE.exists():
            total = int(self.PAUSED_TOTAL_FILE.read_text().strip())
        if self.is_paused and self.PAUSED_AT_FILE.exists():
            paused_at = int(self.PAUSED_AT_FILE.read_text().strip())
            total += int(time.time()) - paused_at
        return total

    def get_duration(self) -> str:
        """Get current recording duration as HH:MM:SS (excludes paused time)."""
        if not self.START_FILE.exists():
            return "00:00:00"

        start = int(self.START_FILE.read_text().strip())
        now = int(time.time())
        duration = max(0, now - start - self._get_paused_total())

        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def get_duration_seconds(self) -> int:
        """Get current recording duration in seconds (excludes paused time)."""
        if not self.START_FILE.exists():
            return 0

        start = int(self.START_FILE.read_text().strip())
        return max(0, int(time.time()) - start - self._get_paused_total())

    def get_current_file(self) -> Path | None:
        """Get the current recording file path."""
        if self.FILE_FILE.exists():
            return Path(self.FILE_FILE.read_text().strip())
        return None

    def start(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Path:
        """Start recording.

        Args:
            progress_callback: Optional callback for status updates.

        Returns:
            Path to the recording file.

        Raises:
            RecordingError: If already recording or start fails.
        """
        if self.is_recording:
            raise RecordingError("Recording already in progress")

        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        filename = f"recording-{timestamp}.mp4"
        temp_dir = self.output_dir / ".recording"
        output_file = temp_dir / filename

        # Ensure temp recording directory exists
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Detect audio sources
        mic_source, sys_source = self._detect_audio_sources()

        # Build ffmpeg command
        if sys_source:
            # Record both mic and system audio
            cmd = [
                "ffmpeg",
                "-f", "pulse", "-i", mic_source,
                "-f", "pulse", "-i", sys_source,
                "-filter_complex", "amerge=inputs=2",
                "-ac", "2",
                "-y", str(output_file),
            ]
        else:
            # Record mic only
            cmd = [
                "ffmpeg",
                "-f", "pulse", "-i", mic_source,
                "-y", str(output_file),
            ]

        if progress_callback:
            progress_callback(f"Starting recording: {filename}")

        # Start ffmpeg process
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Write state files
        self.PID_FILE.write_text(str(self._process.pid))
        self.FILE_FILE.write_text(str(output_file))
        self.START_FILE.write_text(str(int(time.time())))
        self.STATE_FILE.touch()

        if progress_callback:
            progress_callback(f"Recording started (PID: {self._process.pid})")

        return output_file

    def stop(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Path | None:
        """Stop recording.

        Args:
            progress_callback: Optional callback for status updates.

        Returns:
            Path to the recording file, or None if no recording was in progress.
        """
        if not self.is_recording:
            if progress_callback:
                progress_callback("No recording in progress")
            return None

        # Resume if paused so ffmpeg can finalise the file
        if self.is_paused:
            self.resume()

        output_file = self.get_current_file()

        # Get PID and stop process
        if self.PID_FILE.exists():
            try:
                pid = int(self.PID_FILE.read_text().strip())

                # Send SIGINT for clean shutdown
                os.kill(pid, signal.SIGINT)
                time.sleep(2)

                # Force kill if still running
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Already terminated

            except (ValueError, ProcessLookupError):
                pass

        # Clean up state files
        for f in [self.STATE_FILE, self.PID_FILE, self.FILE_FILE, self.START_FILE,
                  self.PAUSE_FILE, self.PAUSED_AT_FILE, self.PAUSED_TOTAL_FILE]:
            if f.exists():
                f.unlink()

        if output_file and output_file.exists():
            # Move from .recording/ temp dir to the watch dir (atomic rename)
            final_file = self.output_dir / output_file.name
            output_file.rename(final_file)

            size = final_file.stat().st_size
            size_str = self._format_size(size)
            if progress_callback:
                progress_callback(f"Recording saved: {final_file.name} ({size_str})")
            return final_file

        if progress_callback:
            progress_callback("Warning: Recording file not found")
        return None

    def pause(self) -> None:
        """Pause the recording by sending SIGSTOP to ffmpeg."""
        if not self.is_recording or self.is_paused:
            return
        if self.PID_FILE.exists():
            pid = int(self.PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGSTOP)
            self.PAUSED_AT_FILE.write_text(str(int(time.time())))
            self.PAUSE_FILE.touch()

    def resume(self) -> None:
        """Resume the recording by sending SIGCONT to ffmpeg."""
        if not self.is_paused:
            return
        if self.PID_FILE.exists():
            pid = int(self.PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGCONT)

        # Accumulate paused duration
        if self.PAUSED_AT_FILE.exists():
            paused_at = int(self.PAUSED_AT_FILE.read_text().strip())
            elapsed = int(time.time()) - paused_at
            prev_total = 0
            if self.PAUSED_TOTAL_FILE.exists():
                prev_total = int(self.PAUSED_TOTAL_FILE.read_text().strip())
            self.PAUSED_TOTAL_FILE.write_text(str(prev_total + elapsed))
            self.PAUSED_AT_FILE.unlink()

        self.PAUSE_FILE.unlink()

    def toggle(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[bool, Path | None]:
        """Toggle recording state.

        Args:
            progress_callback: Optional callback for status updates.

        Returns:
            Tuple of (is_now_recording, file_path).
        """
        if self.is_recording:
            file = self.stop(progress_callback)
            return False, file
        else:
            file = self.start(progress_callback)
            return True, file

    @staticmethod
    def _format_size(size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    def get_status(self) -> dict:
        """Get current recording status.

        Returns:
            Dictionary with status information.
        """
        if self.is_recording:
            return {
                "recording": True,
                "duration": self.get_duration(),
                "duration_seconds": self.get_duration_seconds(),
                "file": str(self.get_current_file()) if self.get_current_file() else None,
            }
        return {
            "recording": False,
            "duration": "00:00:00",
            "duration_seconds": 0,
            "file": None,
        }
