"""Tests for database operations."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.core.database import Database


class TestDatabase:
    """Tests for the Database class."""

    @pytest.fixture
    def db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            database = Database(db_path)
            database.init()
            yield database
            database.close()

    def test_init_creates_tables(self, db):
        """Test that init creates required tables."""
        conn = db._get_conn()

        # Check audio_files table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audio_files'"
        )
        assert cursor.fetchone() is not None

        # Check transcripts table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transcripts'"
        )
        assert cursor.fetchone() is not None

    def test_add_audio(self, db):
        """Test adding an audio file."""
        path = "/test/audio.mp4"
        audio_id = db.add_audio(path)

        assert audio_id > 0
        assert db.audio_exists(path)

    def test_add_audio_duplicate(self, db):
        """Test that adding duplicate audio returns existing ID."""
        path = "/test/audio.mp4"
        id1 = db.add_audio(path)
        id2 = db.add_audio(path)

        assert id1 == id2

    def test_get_audio_id(self, db):
        """Test getting audio ID by path."""
        path = "/test/audio.mp4"
        db.add_audio(path)

        audio_id = db.get_audio_id(path)
        assert audio_id is not None

        # Non-existent path
        assert db.get_audio_id("/nonexistent") is None

    def test_mark_transcribed(self, db):
        """Test marking audio as transcribed."""
        audio_path = "/test/audio.mp4"
        transcript_path = "/test/transcript.yaml"

        db.add_audio(audio_path)
        assert not db.is_transcribed(audio_path)

        db.mark_transcribed(audio_path, transcript_path)
        assert db.is_transcribed(audio_path)

    def test_delete_audio(self, db):
        """Test deleting audio file record."""
        path = "/test/audio.mp4"
        db.add_audio(path)
        assert db.audio_exists(path)

        db.delete_audio(path)
        assert not db.audio_exists(path)

    def test_list_audio_files(self, db):
        """Test listing audio files."""
        db.add_audio("/test/audio1.mp4")
        db.add_audio("/test/audio2.mp4")

        files = db.list_audio_files()
        assert len(files) == 2
        assert all(f.filename in ["audio1.mp4", "audio2.mp4"] for f in files)

    def test_add_transcript(self, db):
        """Test adding a transcript."""
        audio_path = "/test/audio.mp4"
        transcript_path = "/test/transcript.yaml"

        audio_id = db.add_audio(audio_path)
        transcript_id = db.add_transcript(transcript_path, audio_id)

        assert transcript_id > 0

    def test_mark_labeled(self, db):
        """Test marking transcript as labeled."""
        transcript_path = "/test/transcript.yaml"
        db.add_transcript(transcript_path)

        # Should be in unlabeled list
        unlabeled = db.get_unlabeled()
        assert transcript_path in unlabeled

        db.mark_labeled(transcript_path)

        # Should no longer be in unlabeled list
        unlabeled = db.get_unlabeled()
        assert transcript_path not in unlabeled

    def test_mark_summarized(self, db):
        """Test marking transcript as summarized."""
        transcript_path = "/test/transcript.yaml"
        summary_path = "/test/summary.md"

        db.add_transcript(transcript_path)
        db.mark_labeled(transcript_path)

        # Should be in unsummarized list
        unsummarized = db.get_unsummarized()
        assert transcript_path in unsummarized

        db.mark_summarized(transcript_path, summary_path)

        # Should no longer be in unsummarized list
        unsummarized = db.get_unsummarized()
        assert transcript_path not in unsummarized

    def test_get_unlabeled(self, db):
        """Test getting unlabeled transcripts."""
        db.add_transcript("/test/transcript1.yaml")
        db.add_transcript("/test/transcript2.yaml")
        db.add_transcript("/test/transcript3.yaml")

        db.mark_labeled("/test/transcript2.yaml")

        unlabeled = db.get_unlabeled()
        assert len(unlabeled) == 2
        assert "/test/transcript1.yaml" in unlabeled
        assert "/test/transcript3.yaml" in unlabeled
        assert "/test/transcript2.yaml" not in unlabeled

    def test_get_unsummarized(self, db):
        """Test getting unsummarized transcripts."""
        db.add_transcript("/test/transcript1.yaml")
        db.add_transcript("/test/transcript2.yaml")

        # Only labeled transcripts should appear
        assert len(db.get_unsummarized()) == 0

        db.mark_labeled("/test/transcript1.yaml")
        db.mark_labeled("/test/transcript2.yaml")

        unsummarized = db.get_unsummarized()
        assert len(unsummarized) == 2

        db.mark_summarized("/test/transcript1.yaml", "/test/summary1.md")

        unsummarized = db.get_unsummarized()
        assert len(unsummarized) == 1
        assert "/test/transcript2.yaml" in unsummarized

    def test_delete_transcript(self, db):
        """Test deleting transcript record."""
        transcript_path = "/test/transcript.yaml"
        db.add_transcript(transcript_path)

        unlabeled = db.get_unlabeled()
        assert transcript_path in unlabeled

        db.delete_transcript(transcript_path)

        unlabeled = db.get_unlabeled()
        assert transcript_path not in unlabeled

    def test_list_transcripts(self, db):
        """Test listing transcripts."""
        db.add_transcript("/test/transcript1.yaml")
        db.add_transcript("/test/transcript2.yaml")

        transcripts = db.list_transcripts()
        assert len(transcripts) == 2

    def test_get_pending_count(self, db):
        """Test getting pending file count."""
        assert db.get_pending_count() == 0

        db.add_audio("/test/audio1.mp4")
        db.add_audio("/test/audio2.mp4")

        assert db.get_pending_count() == 2

        db.mark_transcribed("/test/audio1.mp4", "/test/transcript.yaml")

        assert db.get_pending_count() == 1

    def test_get_unlabeled_count(self, db):
        """Test getting unlabeled count."""
        assert db.get_unlabeled_count() == 0

        db.add_transcript("/test/transcript1.yaml")
        db.add_transcript("/test/transcript2.yaml")

        assert db.get_unlabeled_count() == 2

        db.mark_labeled("/test/transcript1.yaml")

        assert db.get_unlabeled_count() == 1

    def test_get_unsummarized_count(self, db):
        """Test getting unsummarized count."""
        assert db.get_unsummarized_count() == 0

        db.add_transcript("/test/transcript1.yaml")
        db.mark_labeled("/test/transcript1.yaml")

        assert db.get_unsummarized_count() == 1

        db.mark_summarized("/test/transcript1.yaml", "/test/summary.md")

        assert db.get_unsummarized_count() == 0
