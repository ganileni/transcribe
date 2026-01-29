"""Tests for data models."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.models import AudioFile, Speaker, Transcript, TranscriptData, Utterance


class TestAudioFile:
    """Tests for AudioFile model."""

    def test_status_pending(self):
        """Test that status is pending when not transcribed."""
        audio = AudioFile(path="/test/audio.mp4", filename="audio.mp4")
        assert audio.status == "pending"

    def test_status_transcribed(self):
        """Test that status is transcribed when transcribed_at is set."""
        audio = AudioFile(
            path="/test/audio.mp4",
            filename="audio.mp4",
            transcribed_at=datetime.now(),
        )
        assert audio.status == "transcribed"


class TestTranscript:
    """Tests for Transcript model."""

    def test_status_unlabeled(self):
        """Test status when unlabeled."""
        transcript = Transcript(path="/test/transcript.yaml")
        assert transcript.status == "unlabeled"

    def test_status_labeled(self):
        """Test status when labeled."""
        transcript = Transcript(
            path="/test/transcript.yaml",
            labeled_at=datetime.now(),
        )
        assert transcript.status == "labeled"

    def test_status_summarized(self):
        """Test status when summarized."""
        transcript = Transcript(
            path="/test/transcript.yaml",
            labeled_at=datetime.now(),
            summarized_at=datetime.now(),
        )
        assert transcript.status == "summarized"


class TestSpeaker:
    """Tests for Speaker model."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        speaker = Speaker(id="A", name="Alice")
        d = speaker.to_dict()
        assert d["id"] == "A"
        assert d["name"] == "Alice"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        d = {"id": "B", "name": "Bob"}
        speaker = Speaker.from_dict(d)
        assert speaker.id == "B"
        assert speaker.name == "Bob"

    def test_from_dict_no_name(self):
        """Test deserialization when name is missing."""
        d = {"id": "C"}
        speaker = Speaker.from_dict(d)
        assert speaker.id == "C"
        assert speaker.name is None


class TestUtterance:
    """Tests for Utterance model."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        utt = Utterance(speaker="A", start=1.5, end=3.0, text="Hello world")
        d = utt.to_dict()
        assert d["speaker"] == "A"
        assert d["start"] == 1.5
        assert d["end"] == 3.0
        assert d["text"] == "Hello world"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        d = {"speaker": "B", "start": 2.0, "end": 4.5, "text": "Hi there"}
        utt = Utterance.from_dict(d)
        assert utt.speaker == "B"
        assert utt.start == 2.0
        assert utt.end == 4.5
        assert utt.text == "Hi there"


class TestTranscriptData:
    """Tests for TranscriptData model."""

    @pytest.fixture
    def sample_transcript(self):
        """Create a sample transcript for testing."""
        return TranscriptData(
            source_file="test.mp4",
            transcribed=datetime(2025, 1, 15, 10, 30),
            duration_seconds=120,
            labeled=False,
            speakers=[
                Speaker(id="A", name=None),
                Speaker(id="B", name=None),
            ],
            utterances=[
                Utterance(speaker="A", start=0.0, end=2.5, text="Hello everyone"),
                Utterance(speaker="B", start=2.5, end=5.0, text="Hi there"),
                Utterance(speaker="A", start=5.0, end=8.0, text="Let's get started"),
            ],
        )

    def test_get_speaker_samples(self, sample_transcript):
        """Test getting sample utterances for a speaker."""
        samples = sample_transcript.get_speaker_samples("A", num_samples=2)
        assert len(samples) == 2
        assert "Hello everyone" in samples
        assert "Let's get started" in samples

    def test_get_speaker_by_id(self, sample_transcript):
        """Test getting speaker by ID."""
        speaker = sample_transcript.get_speaker_by_id("A")
        assert speaker is not None
        assert speaker.id == "A"

        # Non-existent speaker
        assert sample_transcript.get_speaker_by_id("Z") is None

    def test_set_speaker_name(self, sample_transcript):
        """Test setting speaker name."""
        result = sample_transcript.set_speaker_name("A", "Alice")
        assert result is True
        assert sample_transcript.get_speaker_by_id("A").name == "Alice"

        # Non-existent speaker
        result = sample_transcript.set_speaker_name("Z", "Zoe")
        assert result is False

    def test_replace_speaker_ids_with_names(self, sample_transcript):
        """Test replacing speaker IDs with names in utterances."""
        sample_transcript.set_speaker_name("A", "Alice")
        sample_transcript.set_speaker_name("B", "Bob")

        sample_transcript.replace_speaker_ids_with_names()

        assert sample_transcript.utterances[0].speaker == "Alice"
        assert sample_transcript.utterances[1].speaker == "Bob"
        assert sample_transcript.utterances[2].speaker == "Alice"

    def test_mark_labeled(self, sample_transcript):
        """Test marking transcript as labeled."""
        assert sample_transcript.labeled is False
        sample_transcript.mark_labeled()
        assert sample_transcript.labeled is True

    def test_get_participants(self, sample_transcript):
        """Test getting participant names."""
        # No names set yet
        assert sample_transcript.get_participants() == []

        sample_transcript.set_speaker_name("A", "Alice")
        sample_transcript.set_speaker_name("B", "Bob")

        participants = sample_transcript.get_participants()
        assert "Alice" in participants
        assert "Bob" in participants

    def test_to_yaml(self, sample_transcript):
        """Test YAML serialization."""
        yaml_str = sample_transcript.to_yaml()

        assert "source_file: test.mp4" in yaml_str
        assert "duration_seconds: 120" in yaml_str
        assert "labeled: false" in yaml_str
        assert 'id: "A"' in yaml_str
        assert 'text: "Hello everyone"' in yaml_str

    def test_yaml_roundtrip(self, sample_transcript):
        """Test YAML serialization and deserialization."""
        yaml_str = sample_transcript.to_yaml()
        loaded = TranscriptData.from_yaml(yaml_str)

        assert loaded.source_file == sample_transcript.source_file
        assert loaded.duration_seconds == sample_transcript.duration_seconds
        assert loaded.labeled == sample_transcript.labeled
        assert len(loaded.speakers) == len(sample_transcript.speakers)
        assert len(loaded.utterances) == len(sample_transcript.utterances)

    def test_save_and_load(self, sample_transcript):
        """Test saving and loading from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "transcript.yaml"

            sample_transcript.save(path)
            assert path.exists()

            loaded = TranscriptData.load(path)
            assert loaded.source_file == sample_transcript.source_file
            assert len(loaded.utterances) == len(sample_transcript.utterances)

    def test_yaml_with_quotes_in_text(self):
        """Test YAML handles quotes in text properly."""
        transcript = TranscriptData(
            source_file="test.mp4",
            transcribed=datetime.now(),
            duration_seconds=10,
            labeled=False,
            speakers=[Speaker(id="A")],
            utterances=[
                Utterance(speaker="A", start=0, end=1, text='He said "hello"'),
            ],
        )

        yaml_str = transcript.to_yaml()
        loaded = TranscriptData.from_yaml(yaml_str)

        # The quote escaping should be handled
        assert "hello" in loaded.utterances[0].text
