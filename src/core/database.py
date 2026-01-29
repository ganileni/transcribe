"""SQLite database operations for the Transcribe application."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterator

from ..models import AudioFile, Transcript


class Database:
    """SQLite database manager for audio files and transcripts."""

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS audio_files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            transcribed_at DATETIME,
            transcript_path TEXT
        );

        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            audio_file_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            labeled_at DATETIME,
            summarized_at DATETIME,
            summary_path TEXT,
            FOREIGN KEY (audio_file_id) REFERENCES audio_files(id)
        );

        CREATE INDEX IF NOT EXISTS idx_audio_files_path ON audio_files(path);
        CREATE INDEX IF NOT EXISTS idx_transcripts_path ON transcripts(path);
        CREATE INDEX IF NOT EXISTS idx_transcripts_labeled ON transcripts(labeled_at);
    """

    def __init__(self, db_path: str | Path):
        """Initialize database connection.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init(self) -> None:
        """Initialize database schema."""
        conn = self._get_conn()
        conn.executescript(self.SCHEMA)
        conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # Audio file operations

    def add_audio(self, path: str | Path) -> int:
        """Add or get an audio file record.

        Args:
            path: Path to the audio file.

        Returns:
            The audio file ID.
        """
        path = str(path)
        filename = Path(path).name
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT OR IGNORE INTO audio_files (path, filename) VALUES (?, ?)",
            (path, filename),
        )
        conn.commit()

        if cursor.lastrowid:
            return cursor.lastrowid
        # File already existed, get its ID
        return self.get_audio_id(path) or 0

    def get_audio_id(self, path: str | Path) -> int | None:
        """Get audio file ID by path.

        Args:
            path: Path to the audio file.

        Returns:
            The audio file ID or None if not found.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id FROM audio_files WHERE path = ?", (str(path),)
        ).fetchone()
        return row["id"] if row else None

    def mark_transcribed(self, audio_path: str | Path, transcript_path: str | Path) -> None:
        """Mark an audio file as transcribed.

        Args:
            audio_path: Path to the audio file.
            transcript_path: Path to the transcript file.
        """
        conn = self._get_conn()
        conn.execute(
            """UPDATE audio_files
               SET transcribed_at = CURRENT_TIMESTAMP, transcript_path = ?
               WHERE path = ?""",
            (str(transcript_path), str(audio_path)),
        )
        conn.commit()

    def audio_exists(self, path: str | Path) -> bool:
        """Check if an audio file exists in the database.

        Args:
            path: Path to the audio file.

        Returns:
            True if the file exists in the database.
        """
        return self.get_audio_id(path) is not None

    def is_transcribed(self, path: str | Path) -> bool:
        """Check if an audio file has been transcribed.

        Args:
            path: Path to the audio file.

        Returns:
            True if the file has been transcribed.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT transcribed_at FROM audio_files WHERE path = ?", (str(path),)
        ).fetchone()
        return row is not None and row["transcribed_at"] is not None

    def delete_audio(self, path: str | Path) -> None:
        """Delete an audio file record.

        Args:
            path: Path to the audio file.
        """
        conn = self._get_conn()
        conn.execute("DELETE FROM audio_files WHERE path = ?", (str(path),))
        conn.commit()

    def list_audio_files(self) -> list[AudioFile]:
        """List all audio files with their status.

        Returns:
            List of AudioFile objects.
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT id, path, filename, added_at, transcribed_at, transcript_path
               FROM audio_files ORDER BY added_at DESC"""
        ).fetchall()

        result = []
        for row in rows:
            added_at = None
            if row["added_at"]:
                added_at = datetime.fromisoformat(row["added_at"])
            transcribed_at = None
            if row["transcribed_at"]:
                transcribed_at = datetime.fromisoformat(row["transcribed_at"])

            result.append(
                AudioFile(
                    id=row["id"],
                    path=row["path"],
                    filename=row["filename"],
                    added_at=added_at,
                    transcribed_at=transcribed_at,
                    transcript_path=row["transcript_path"],
                )
            )
        return result

    # Transcript operations

    def add_transcript(self, path: str | Path, audio_file_id: int | None = None) -> int:
        """Add a transcript record.

        Args:
            path: Path to the transcript file.
            audio_file_id: Optional ID of the associated audio file.

        Returns:
            The transcript ID.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT OR IGNORE INTO transcripts (path, audio_file_id) VALUES (?, ?)",
            (str(path), audio_file_id),
        )
        conn.commit()

        if cursor.lastrowid:
            return cursor.lastrowid
        # Already existed
        row = conn.execute(
            "SELECT id FROM transcripts WHERE path = ?", (str(path),)
        ).fetchone()
        return row["id"] if row else 0

    def mark_labeled(self, transcript_path: str | Path) -> None:
        """Mark a transcript as labeled.

        Args:
            transcript_path: Path to the transcript file.
        """
        conn = self._get_conn()
        conn.execute(
            "UPDATE transcripts SET labeled_at = CURRENT_TIMESTAMP WHERE path = ?",
            (str(transcript_path),),
        )
        conn.commit()

    def mark_summarized(self, transcript_path: str | Path, summary_path: str | Path) -> None:
        """Mark a transcript as summarized.

        Args:
            transcript_path: Path to the transcript file.
            summary_path: Path to the summary file.
        """
        conn = self._get_conn()
        conn.execute(
            """UPDATE transcripts
               SET summarized_at = CURRENT_TIMESTAMP, summary_path = ?
               WHERE path = ?""",
            (str(summary_path), str(transcript_path)),
        )
        conn.commit()

    def delete_transcript(self, path: str | Path) -> None:
        """Delete a transcript record.

        Args:
            path: Path to the transcript file.
        """
        conn = self._get_conn()
        conn.execute("DELETE FROM transcripts WHERE path = ?", (str(path),))
        conn.commit()

    def get_unlabeled(self) -> list[str]:
        """Get paths of unlabeled transcripts.

        Returns:
            List of transcript file paths.
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT path FROM transcripts WHERE labeled_at IS NULL ORDER BY created_at"
        ).fetchall()
        return [row["path"] for row in rows]

    def get_unsummarized(self) -> list[str]:
        """Get paths of labeled but unsummarized transcripts.

        Returns:
            List of transcript file paths.
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT path FROM transcripts
               WHERE labeled_at IS NOT NULL AND summarized_at IS NULL
               ORDER BY created_at"""
        ).fetchall()
        return [row["path"] for row in rows]

    def list_transcripts(self) -> list[Transcript]:
        """List all transcripts with their status.

        Returns:
            List of Transcript objects.
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT id, path, audio_file_id, created_at, labeled_at, summarized_at, summary_path
               FROM transcripts ORDER BY created_at DESC"""
        ).fetchall()

        result = []
        for row in rows:
            created_at = None
            if row["created_at"]:
                created_at = datetime.fromisoformat(row["created_at"])
            labeled_at = None
            if row["labeled_at"]:
                labeled_at = datetime.fromisoformat(row["labeled_at"])
            summarized_at = None
            if row["summarized_at"]:
                summarized_at = datetime.fromisoformat(row["summarized_at"])

            result.append(
                Transcript(
                    id=row["id"],
                    path=row["path"],
                    audio_file_id=row["audio_file_id"],
                    created_at=created_at,
                    labeled_at=labeled_at,
                    summarized_at=summarized_at,
                    summary_path=row["summary_path"],
                )
            )
        return result

    # Statistics

    def get_pending_count(self) -> int:
        """Get count of files pending transcription."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as count FROM audio_files WHERE transcribed_at IS NULL"
        ).fetchone()
        return row["count"]

    def get_pending_audio_files(self) -> list[AudioFile]:
        """Get all audio files pending transcription.

        Returns:
            List of AudioFile objects that haven't been transcribed yet.
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT id, path, filename, added_at, transcribed_at, transcript_path
               FROM audio_files WHERE transcribed_at IS NULL ORDER BY added_at ASC"""
        ).fetchall()

        result = []
        for row in rows:
            added_at = None
            if row["added_at"]:
                added_at = datetime.fromisoformat(row["added_at"])

            result.append(
                AudioFile(
                    id=row["id"],
                    path=row["path"],
                    filename=row["filename"],
                    added_at=added_at,
                    transcribed_at=None,
                    transcript_path=None,
                )
            )
        return result

    def get_unlabeled_count(self) -> int:
        """Get count of unlabeled transcripts."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as count FROM transcripts WHERE labeled_at IS NULL"
        ).fetchone()
        return row["count"]

    def get_unsummarized_count(self) -> int:
        """Get count of unsummarized transcripts."""
        conn = self._get_conn()
        row = conn.execute(
            """SELECT COUNT(*) as count FROM transcripts
               WHERE labeled_at IS NOT NULL AND summarized_at IS NULL"""
        ).fetchone()
        return row["count"]
