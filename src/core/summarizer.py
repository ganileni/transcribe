"""Claude CLI integration for transcript summarization."""

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..models import TranscriptData


class SummarizationError(Exception):
    """Error during summarization."""

    pass


class Summarizer:
    """Summarizes transcripts using Claude CLI."""

    def __init__(self, prompt_file: str | Path | None = None):
        """Initialize the summarizer.

        Args:
            prompt_file: Path to the summarization prompt template.
                        Defaults to assets/summarisation-prompt.md in the repo.
        """
        if prompt_file:
            self.prompt_file = Path(prompt_file)
        else:
            # Find the prompt file relative to this module
            module_dir = Path(__file__).parent.parent.parent
            self.prompt_file = module_dir / "assets" / "summarisation-prompt.md"

    def _check_claude_available(self) -> None:
        """Check if claude CLI is available."""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise SummarizationError("claude CLI returned an error")
        except FileNotFoundError:
            raise SummarizationError(
                "claude CLI not found. Install Claude Code for summarization."
            )

    def _load_prompt_template(self) -> str:
        """Load the prompt template."""
        if not self.prompt_file.exists():
            raise SummarizationError(f"Prompt template not found: {self.prompt_file}")
        return self.prompt_file.read_text()

    def _get_transcript_date(self, transcript: TranscriptData, transcript_path: Path) -> str:
        """Extract date from transcript filename or transcribed time."""
        # Try to extract from filename (format: YYYY-MM-DD-HH-MM-...)
        match = re.match(r"^(\d{4}-\d{2}-\d{2})", transcript_path.name)
        if match:
            return match.group(1)
        return transcript.transcribed.strftime("%Y-%m-%d")

    def _get_wikilink(self, transcript_path: Path) -> str:
        """Get relative path for Obsidian wikilink."""
        return f"raw-transcription/{transcript_path.stem}"

    def _get_summary_filename(
        self, transcript_path: Path, title: str, participants: list[str]
    ) -> str:
        """Generate summary filename from date, participants, and title."""
        # Extract date
        match = re.match(r"^(\d{4}-\d{2}-\d{2})", transcript_path.name)
        date = match.group(1) if match else datetime.now().strftime("%Y-%m-%d")

        # Slugify participants and title
        participants_slug = "-".join(
            re.sub(r"[^a-z0-9]", "", p.lower()) for p in participants[:2]
        )
        title_slug = re.sub(r"[^a-z0-9-]", "", title.lower().replace(" ", "-"))
        title_slug = re.sub(r"-+", "-", title_slug).strip("-")[:50]

        parts = [date]
        if participants_slug:
            parts.append(participants_slug)
        if title_slug:
            parts.append(title_slug)

        return "-".join(parts) + ".md"

    def _extract_title(self, summary: str) -> str:
        """Extract meeting title from Claude's output.

        Args:
            summary: The full summary output from Claude.

        Returns:
            The extracted title, or "Meeting" if not found.
        """
        # Look for ### Meeting Title section
        match = re.search(
            r"###\s*Meeting\s*Title\s*\n+([^\n#]+)", summary, re.IGNORECASE
        )
        if match:
            title = match.group(1).strip()
            # Remove any markdown formatting
            title = re.sub(r"[*_`]", "", title)
            return title
        return "Meeting"

    def build_prompt(
        self,
        transcript: TranscriptData,
        transcript_path: Path,
        title: str,
    ) -> str:
        """Build the full prompt for Claude.

        Args:
            transcript: The transcript data.
            transcript_path: Path to the transcript file.
            title: Meeting title.

        Returns:
            The complete prompt string.
        """
        template = self._load_prompt_template()
        date = self._get_transcript_date(transcript, transcript_path)
        participants = ", ".join(transcript.get_participants())
        wikilink = self._get_wikilink(transcript_path)

        # Load transcript content
        content = transcript_path.read_text()

        prompt = f"""{template}

Meeting Title: {title}
Date: {date}
Participants: {participants}
Raw Transcript Link: [[{wikilink}]]

--- BEGIN TRANSCRIPT ---
{content}
--- END TRANSCRIPT ---"""

        return prompt

    def summarize(
        self,
        transcript_path: str | Path,
        title: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[str, str]:
        """Summarize a transcript using Claude CLI.

        Args:
            transcript_path: Path to the transcript YAML file.
            title: Meeting title (fallback if Claude doesn't generate one).
            progress_callback: Optional callback for progress updates.

        Returns:
            Tuple of (summary_text, generated_title).

        Raises:
            SummarizationError: If summarization fails.
        """
        self._check_claude_available()

        transcript_path = Path(transcript_path)
        if not transcript_path.exists():
            raise SummarizationError(f"Transcript not found: {transcript_path}")

        transcript = TranscriptData.load(transcript_path)

        if progress_callback:
            progress_callback("Building prompt...")

        prompt = self.build_prompt(transcript, transcript_path, title)

        if progress_callback:
            progress_callback("Generating summary with Claude...")

        # Call Claude CLI
        result = subprocess.run(
            ["claude", "-p"],
            input=prompt,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise SummarizationError(f"Claude CLI error: {result.stderr}")

        summary = result.stdout.strip()
        generated_title = self._extract_title(summary)

        return summary, generated_title

    def summarize_and_save(
        self,
        transcript_path: str | Path,
        title: str,
        output_dir: str | Path,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[Path, str]:
        """Summarize a transcript and save the result.

        Args:
            transcript_path: Path to the transcript YAML file.
            title: Meeting title (fallback if Claude doesn't generate one).
            output_dir: Directory to save the summary.
            progress_callback: Optional callback for progress updates.

        Returns:
            Tuple of (path_to_summary_file, generated_title).
        """
        transcript_path = Path(transcript_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        transcript = TranscriptData.load(transcript_path)
        summary, generated_title = self.summarize(transcript_path, title, progress_callback)

        # Build output file
        date = self._get_transcript_date(transcript, transcript_path)
        participants_list = transcript.get_participants()
        participants = ", ".join(participants_list)
        wikilink = self._get_wikilink(transcript_path)
        output_filename = self._get_summary_filename(
            transcript_path, generated_title, participants_list
        )
        output_file = output_dir / output_filename

        # Write output with frontmatter
        output_content = f"""---
date: {date}
title: {generated_title}
participants: [{participants}]
---

> Raw transcript: [[{wikilink}]]

{summary}
"""
        output_file.write_text(output_content)

        if progress_callback:
            progress_callback(f"Summary saved to: {output_file}")

        return output_file, generated_title
