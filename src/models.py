"""Data models for the Transcribe application."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AudioFile:
    """Represents an audio file in the database."""

    path: str
    filename: str
    id: int | None = None
    added_at: datetime | None = None
    transcribed_at: datetime | None = None
    transcript_path: str | None = None

    @property
    def status(self) -> str:
        """Get the status of this audio file."""
        if self.transcribed_at:
            return "transcribed"
        return "pending"


@dataclass
class Transcript:
    """Represents a transcript record in the database."""

    path: str
    id: int | None = None
    audio_file_id: int | None = None
    created_at: datetime | None = None
    labeled_at: datetime | None = None
    summarized_at: datetime | None = None
    summary_path: str | None = None

    @property
    def status(self) -> str:
        """Get the status of this transcript."""
        if self.summarized_at:
            return "summarized"
        if self.labeled_at:
            return "labeled"
        return "unlabeled"


@dataclass
class Speaker:
    """Represents a speaker in a transcript."""

    id: str
    name: str | None = None
    samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Speaker":
        """Create from dictionary."""
        return cls(id=data["id"], name=data.get("name"))


@dataclass
class Utterance:
    """Represents a single utterance in a transcript."""

    speaker: str
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "speaker": self.speaker,
            "start": self.start,
            "end": self.end,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Utterance":
        """Create from dictionary."""
        return cls(
            speaker=data["speaker"],
            start=data["start"],
            end=data["end"],
            text=data["text"],
        )


@dataclass
class TranscriptData:
    """Complete transcript data with metadata and utterances."""

    source_file: str
    transcribed: datetime
    duration_seconds: int
    labeled: bool
    speakers: list[Speaker]
    utterances: list[Utterance]

    def get_speaker_samples(self, speaker_id: str, num_samples: int = 3) -> list[str]:
        """Get sample utterances for a speaker."""
        samples = []
        for utt in self.utterances:
            if utt.speaker == speaker_id:
                samples.append(utt.text)
                if len(samples) >= num_samples:
                    break
        return samples

    def get_speaker_by_id(self, speaker_id: str) -> Speaker | None:
        """Get a speaker by their ID."""
        for speaker in self.speakers:
            if speaker.id == speaker_id:
                return speaker
        return None

    def set_speaker_name(self, speaker_id: str, name: str) -> bool:
        """Set the name for a speaker."""
        speaker = self.get_speaker_by_id(speaker_id)
        if speaker:
            speaker.name = name
            return True
        return False

    def replace_speaker_ids_with_names(self) -> None:
        """Replace speaker IDs with names in utterances."""
        id_to_name = {s.id: s.name for s in self.speakers if s.name}
        for utt in self.utterances:
            if utt.speaker in id_to_name:
                utt.speaker = id_to_name[utt.speaker]

    def mark_labeled(self) -> None:
        """Mark the transcript as labeled."""
        self.labeled = True

    def get_participants(self) -> list[str]:
        """Get list of participant names."""
        return [s.name for s in self.speakers if s.name]

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        # Build the document with explicit formatting
        lines = [
            "---",
            f"source_file: {self.source_file}",
            f"transcribed: {self.transcribed.isoformat()}",
            f"duration_seconds: {self.duration_seconds}",
            f"labeled: {str(self.labeled).lower()}",
            "speakers:",
        ]

        for speaker in self.speakers:
            lines.append(f'  - id: "{speaker.id}"')
            if speaker.name:
                lines.append(f'    name: "{speaker.name}"')
            else:
                lines.append("    name: null")

        lines.append("---")
        lines.append("utterances:")

        for utt in self.utterances:
            # Escape quotes in text
            text = utt.text.replace('"', '\\"')
            lines.append(f'  - speaker: "{utt.speaker}"')
            lines.append(f"    start: {utt.start}")
            lines.append(f"    end: {utt.end}")
            lines.append(f'    text: "{text}"')

        return "\n".join(lines)

    def save(self, path: str | Path) -> None:
        """Save transcript to a file."""
        Path(path).write_text(self.to_yaml())

    @classmethod
    def from_yaml(cls, content: str) -> "TranscriptData":
        """Parse transcript from YAML string."""
        # Split into documents (frontmatter and utterances)
        docs = list(yaml.safe_load_all(content))

        if len(docs) < 2:
            raise ValueError("Invalid transcript format: expected two YAML documents")

        frontmatter = docs[0]
        utterance_data = docs[1]

        # Parse transcribed datetime
        transcribed = frontmatter["transcribed"]
        if isinstance(transcribed, str):
            transcribed = datetime.fromisoformat(transcribed)

        # Parse speakers
        speakers = [Speaker.from_dict(s) for s in frontmatter.get("speakers", [])]

        # Parse utterances
        utterances = [Utterance.from_dict(u) for u in utterance_data.get("utterances", [])]

        return cls(
            source_file=frontmatter["source_file"],
            transcribed=transcribed,
            duration_seconds=frontmatter["duration_seconds"],
            labeled=frontmatter.get("labeled", False),
            speakers=speakers,
            utterances=utterances,
        )

    @classmethod
    def load(cls, path: str | Path) -> "TranscriptData":
        """Load transcript from a file."""
        content = Path(path).read_text()
        return cls.from_yaml(content)
