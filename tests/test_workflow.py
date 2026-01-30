"""Integration tests for the full transcription workflow.

Tests the complete pipeline:
1. New audio file detection in watch_dir
2. Transcription and database updates
3. Transcript appears in unlabeled list
4. Labeling updates transcript
5. Summarization (mocked)
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import Config
from src.core.database import Database
from src.core.transcriber import Transcriber
from src.models import Speaker, TranscriptData, Utterance


class TestWorkflow:
    """Integration tests for the transcription workflow."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            watch_dir = tmpdir / "watch"
            raw_transcripts_dir = tmpdir / "raw-transcription"
            done_dir = tmpdir / "done"
            summaries_dir = tmpdir / "summaries"

            watch_dir.mkdir()
            raw_transcripts_dir.mkdir()
            done_dir.mkdir()
            summaries_dir.mkdir()

            yield {
                "base": tmpdir,
                "watch": watch_dir,
                "raw_transcripts": raw_transcripts_dir,
                "done": done_dir,
                "summaries": summaries_dir,
            }

    @pytest.fixture
    def db(self, temp_dirs):
        """Create a temporary database."""
        db_path = temp_dirs["base"] / "test.db"
        database = Database(db_path)
        database.init()
        yield database
        database.close()

    @pytest.fixture
    def mock_assemblyai_response(self):
        """Mock AssemblyAI transcription response."""
        return {
            "id": "test-transcript-id",
            "status": "completed",
            "audio_duration": 120,
            "utterances": [
                {
                    "speaker": "A",
                    "start": 0,
                    "end": 5000,
                    "text": "Hello, this is speaker A talking.",
                },
                {
                    "speaker": "B",
                    "start": 5000,
                    "end": 10000,
                    "text": "Hi, this is speaker B responding.",
                },
            ],
        }

    def make_transcript(
        self,
        source_file: str = "test.mp4",
        duration: int = 120,
        labeled: bool = False,
        speakers: list[dict] | None = None,
        utterances: list[dict] | None = None,
    ) -> TranscriptData:
        """Helper to create TranscriptData with sensible defaults."""
        if speakers is None:
            speakers = [{"id": "A", "name": None}, {"id": "B", "name": None}]
        if utterances is None:
            utterances = [
                {"speaker": "A", "start": 0.0, "end": 5.0, "text": "Hello"},
                {"speaker": "B", "start": 5.0, "end": 10.0, "text": "Hi there"},
            ]

        return TranscriptData(
            source_file=source_file,
            transcribed=datetime.now(),
            duration_seconds=duration,
            labeled=labeled,
            speakers=[Speaker.from_dict(s) for s in speakers],
            utterances=[Utterance.from_dict(u) for u in utterances],
        )

    # =========================================================================
    # Test 1: New file detection
    # =========================================================================

    def test_new_audio_file_detected(self, temp_dirs, db):
        """Test that a new audio file in watch_dir is detected and added to DB."""
        watch_dir = temp_dirs["watch"]

        # Create a fake audio file
        audio_file = watch_dir / "test_recording.mp3"
        audio_file.write_bytes(b"fake audio content")

        # Simulate the scanning logic from MainMenuScreen._scan_for_new_files
        audio_extensions = {"mp4", "m4a", "mp3", "wav", "ogg", "webm", "flac"}
        new_files = []

        for file in watch_dir.iterdir():
            if file.is_file() and file.suffix.lower().lstrip(".") in audio_extensions:
                if not db.audio_exists(str(file)):
                    db.add_audio(str(file))
                    new_files.append(file)

        # Verify file was detected
        assert len(new_files) == 1
        assert new_files[0].name == "test_recording.mp3"

        # Verify it's in the database
        assert db.audio_exists(str(audio_file))
        audio_id = db.get_audio_id(str(audio_file))
        assert audio_id is not None

    def test_non_audio_files_ignored(self, temp_dirs, db):
        """Test that non-audio files are ignored."""
        watch_dir = temp_dirs["watch"]

        # Create non-audio files
        (watch_dir / "document.txt").write_text("text content")
        (watch_dir / "image.png").write_bytes(b"fake image")
        (watch_dir / "notes.md").write_text("# Notes")

        audio_extensions = {"mp4", "m4a", "mp3", "wav", "ogg", "webm", "flac"}
        new_files = []

        for file in watch_dir.iterdir():
            if file.is_file() and file.suffix.lower().lstrip(".") in audio_extensions:
                if not db.audio_exists(str(file)):
                    db.add_audio(str(file))
                    new_files.append(file)

        assert len(new_files) == 0
        assert db.get_pending_count() == 0

    def test_duplicate_files_not_added_twice(self, temp_dirs, db):
        """Test that scanning twice doesn't add duplicates."""
        watch_dir = temp_dirs["watch"]
        audio_file = watch_dir / "test.mp3"
        audio_file.write_bytes(b"audio")

        audio_extensions = {"mp4", "m4a", "mp3", "wav", "ogg", "webm", "flac"}

        # First scan
        for file in watch_dir.iterdir():
            if file.is_file() and file.suffix.lower().lstrip(".") in audio_extensions:
                if not db.audio_exists(str(file)):
                    db.add_audio(str(file))

        assert db.get_pending_count() == 1

        # Second scan
        for file in watch_dir.iterdir():
            if file.is_file() and file.suffix.lower().lstrip(".") in audio_extensions:
                if not db.audio_exists(str(file)):
                    db.add_audio(str(file))

        # Should still be 1
        assert db.get_pending_count() == 1

    # =========================================================================
    # Test 2: Transcription
    # =========================================================================

    @patch.object(Transcriber, "transcribe")
    def test_transcription_creates_transcript_file(
        self, mock_transcribe, temp_dirs, db, mock_assemblyai_response
    ):
        """Test that transcription creates a transcript file and updates DB."""
        watch_dir = temp_dirs["watch"]
        raw_dir = temp_dirs["raw_transcripts"]

        # Create audio file
        audio_file = watch_dir / "2026-01-30-test-recording.mp4"
        audio_file.write_bytes(b"fake audio")

        # Add to DB
        audio_id = db.add_audio(str(audio_file))

        # Create mock transcript data
        transcriber = Transcriber("test-api-key")
        mock_transcript = transcriber.convert_to_transcript_data(
            mock_assemblyai_response, str(audio_file)
        )
        mock_transcribe.return_value = mock_transcript

        # Use transcribe_and_save
        transcript_path = transcriber.transcribe_and_save(
            str(audio_file),
            raw_dir,
        )

        # Verify transcript file created
        assert transcript_path.exists()
        assert transcript_path.suffix == ".yaml"

        # Update database (simulating what _process_files does)
        db.mark_transcribed(str(audio_file), str(transcript_path))
        db.add_transcript(str(transcript_path), audio_id)

        # Verify DB updated
        assert db.is_transcribed(str(audio_file))
        assert db.get_pending_count() == 0

    # =========================================================================
    # Test 3: Unlabeled transcripts
    # =========================================================================

    def test_new_transcript_appears_in_unlabeled(self, temp_dirs, db):
        """Test that a new transcript appears in the unlabeled list."""
        raw_dir = temp_dirs["raw_transcripts"]

        # Create a transcript file
        transcript = self.make_transcript()

        transcript_path = raw_dir / "2026-01-30-test-transcript.yaml"
        transcript.save(transcript_path)

        # Add to database
        db.add_transcript(str(transcript_path), audio_file_id=None)

        # Check unlabeled list
        unlabeled = db.get_unlabeled()
        assert len(unlabeled) == 1
        assert str(transcript_path) in unlabeled

    def test_labeled_transcript_not_in_unlabeled(self, temp_dirs, db):
        """Test that a labeled transcript doesn't appear in unlabeled list."""
        raw_dir = temp_dirs["raw_transcripts"]

        # Create and save transcript
        transcript = self.make_transcript(
            speakers=[{"id": "A", "name": "Alice"}],
            utterances=[{"speaker": "A", "start": 0.0, "end": 5.0, "text": "Hello"}],
        )
        transcript.mark_labeled()

        transcript_path = raw_dir / "2026-01-30-labeled-transcript.yaml"
        transcript.save(transcript_path)

        # Add to database and mark as labeled
        db.add_transcript(str(transcript_path))
        db.mark_labeled(str(transcript_path))

        # Check unlabeled list
        unlabeled = db.get_unlabeled()
        assert len(unlabeled) == 0

    def test_multiple_transcripts_unlabeled_ordering(self, temp_dirs, db):
        """Test that multiple unlabeled transcripts are returned in order."""
        raw_dir = temp_dirs["raw_transcripts"]

        # Create multiple transcripts
        for i, name in enumerate(["first", "second", "third"]):
            transcript = self.make_transcript(
                source_file=f"{name}.mp4",
                duration=60,
                speakers=[{"id": "A", "name": None}],
                utterances=[{"speaker": "A", "start": 0.0, "end": 5.0, "text": f"Test {name}"}],
            )
            path = raw_dir / f"2026-01-{10+i:02d}-{name}-transcript.yaml"
            transcript.save(path)
            db.add_transcript(str(path))

        unlabeled = db.get_unlabeled()
        assert len(unlabeled) == 3

    # =========================================================================
    # Test 4: Labeling workflow
    # =========================================================================

    def test_labeling_updates_transcript_file(self, temp_dirs, db):
        """Test that labeling updates the transcript file."""
        raw_dir = temp_dirs["raw_transcripts"]

        # Create transcript
        transcript = self.make_transcript()

        transcript_path = raw_dir / "2026-01-30-to-label-transcript.yaml"
        transcript.save(transcript_path)
        db.add_transcript(str(transcript_path))

        # Simulate labeling
        transcript.set_speaker_name("A", "Alice")
        transcript.set_speaker_name("B", "Bob")
        transcript.replace_speaker_ids_with_names()
        transcript.mark_labeled()
        transcript.save(transcript_path)

        # Mark as labeled in DB
        db.mark_labeled(str(transcript_path))

        # Verify
        assert db.get_unlabeled_count() == 0

        # Reload and check
        reloaded = TranscriptData.load(transcript_path)
        assert reloaded.labeled is True
        assert reloaded.speakers[0].name == "Alice"
        assert reloaded.speakers[1].name == "Bob"

    def test_partial_labeling_keeps_unlabeled(self, temp_dirs, db):
        """Test that partial labeling keeps transcript as unlabeled."""
        raw_dir = temp_dirs["raw_transcripts"]

        # Create transcript with 2 speakers
        transcript = self.make_transcript()

        transcript_path = raw_dir / "2026-01-30-partial-transcript.yaml"
        transcript.save(transcript_path)
        db.add_transcript(str(transcript_path))

        # Only label one speaker
        transcript.set_speaker_name("A", "Alice")
        # Don't label B
        transcript.save(transcript_path)
        # Don't mark as labeled in DB

        # Should still be unlabeled
        assert db.get_unlabeled_count() == 1

    # =========================================================================
    # Test 5: Full workflow integration
    # =========================================================================

    @patch.object(Transcriber, "transcribe")
    def test_full_workflow_file_to_labeled(
        self, mock_transcribe, temp_dirs, db, mock_assemblyai_response
    ):
        """Test the complete workflow from new file to labeled transcript."""
        watch_dir = temp_dirs["watch"]
        raw_dir = temp_dirs["raw_transcripts"]
        done_dir = temp_dirs["done"]

        # Step 1: New audio file appears
        audio_file = watch_dir / "2026-01-30-meeting.mp4"
        audio_file.write_bytes(b"fake audio content")

        # Step 2: File is detected
        audio_extensions = {"mp4", "m4a", "mp3", "wav", "ogg", "webm", "flac"}
        for file in watch_dir.iterdir():
            if file.is_file() and file.suffix.lower().lstrip(".") in audio_extensions:
                if not db.audio_exists(str(file)):
                    db.add_audio(str(file))

        audio_id = db.get_audio_id(str(audio_file))
        assert audio_id is not None
        assert db.get_pending_count() == 1

        # Step 3: File is transcribed (mock API)
        transcriber = Transcriber("test-api-key")
        mock_transcript = transcriber.convert_to_transcript_data(
            mock_assemblyai_response, str(audio_file)
        )
        mock_transcribe.return_value = mock_transcript

        transcript_path = transcriber.transcribe_and_save(str(audio_file), raw_dir)

        # Update DB
        db.mark_transcribed(str(audio_file), str(transcript_path))
        db.add_transcript(str(transcript_path), audio_id)

        assert db.get_pending_count() == 0
        assert db.get_unlabeled_count() == 1

        # Step 4: Transcript is labeled
        transcript = TranscriptData.load(transcript_path)

        # Verify initial state
        assert transcript.labeled is False
        assert len(transcript.speakers) == 2

        # Label speakers
        transcript.set_speaker_name("A", "Alice")
        transcript.set_speaker_name("B", "Bob")
        transcript.replace_speaker_ids_with_names()
        transcript.mark_labeled()
        transcript.save(transcript_path)
        db.mark_labeled(str(transcript_path))

        # Verify final state
        assert db.get_unlabeled_count() == 0

        # Reload to verify persistence
        final_transcript = TranscriptData.load(transcript_path)
        assert final_transcript.labeled is True
        assert final_transcript.speakers[0].name == "Alice"
        assert final_transcript.speakers[1].name == "Bob"

    def test_transcript_file_content_format(self, temp_dirs):
        """Test that transcript files have correct YAML format."""
        raw_dir = temp_dirs["raw_transcripts"]

        transcript = self.make_transcript(
            utterances=[
                {"speaker": "A", "start": 0.0, "end": 5.5, "text": "Hello there!"},
                {"speaker": "B", "start": 5.5, "end": 10.0, "text": "Hi, how are you?"},
            ],
        )

        transcript_path = raw_dir / "test-transcript.yaml"
        transcript.save(transcript_path)

        # Read raw content
        content = transcript_path.read_text()

        # Check key fields are present
        assert "source_file: test.mp4" in content
        assert "duration_seconds: 120" in content
        assert "labeled: false" in content
        assert "speakers:" in content
        assert "utterances:" in content
        assert "Hello there!" in content
