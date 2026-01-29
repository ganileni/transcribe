"""Tests for the transcriber module."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.transcriber import TranscriptionError, Transcriber


class TestTranscriber:
    """Tests for the Transcriber class."""

    @pytest.fixture
    def transcriber(self):
        """Create a transcriber with a test API key."""
        return Transcriber("test-api-key")

    @pytest.fixture
    def mock_response(self):
        """Create a mock AssemblyAI response."""
        return {
            "id": "test-transcript-id",
            "status": "completed",
            "audio_duration": 120,
            "utterances": [
                {
                    "speaker": "A",
                    "start": 0,
                    "end": 2500,
                    "text": "Hello everyone, welcome to the meeting.",
                },
                {
                    "speaker": "B",
                    "start": 2500,
                    "end": 5000,
                    "text": "Thanks for having me.",
                },
                {
                    "speaker": "A",
                    "start": 5000,
                    "end": 8000,
                    "text": "Let's discuss the project updates.",
                },
            ],
        }

    def test_convert_to_transcript_data(self, transcriber, mock_response):
        """Test converting AssemblyAI response to TranscriptData."""
        transcript = transcriber.convert_to_transcript_data(mock_response, "/test/audio.mp4")

        assert transcript.source_file == "audio.mp4"
        assert transcript.duration_seconds == 120
        assert transcript.labeled is False

        # Check speakers
        assert len(transcript.speakers) == 2
        speaker_ids = [s.id for s in transcript.speakers]
        assert "A" in speaker_ids
        assert "B" in speaker_ids

        # Check utterances
        assert len(transcript.utterances) == 3
        assert transcript.utterances[0].speaker == "A"
        assert transcript.utterances[0].start == 0.0
        assert transcript.utterances[0].end == 2.5  # Converted from ms
        assert "Hello everyone" in transcript.utterances[0].text

    def test_convert_handles_empty_utterances(self, transcriber):
        """Test handling of empty utterances."""
        response = {
            "status": "completed",
            "audio_duration": 60,
            "utterances": [],
        }

        transcript = transcriber.convert_to_transcript_data(response, "/test/audio.mp4")
        assert len(transcript.speakers) == 0
        assert len(transcript.utterances) == 0

    @patch("src.core.transcriber.requests.Session")
    def test_upload_success(self, mock_session_class, transcriber):
        """Test successful file upload."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"upload_url": "https://example.com/upload"}
        mock_session.post.return_value = mock_response
        transcriber.session = mock_session

        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            f.write(b"test audio content")
            f.flush()

            url = transcriber.upload(f.name)

            assert url == "https://example.com/upload"
            mock_session.post.assert_called_once()

    @patch("src.core.transcriber.requests.Session")
    def test_upload_failure(self, mock_session_class, transcriber):
        """Test upload failure handling."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_session.post.return_value = mock_response
        transcriber.session = mock_session

        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            f.write(b"test")
            f.flush()

            with pytest.raises(TranscriptionError) as exc:
                transcriber.upload(f.name)

            assert "Upload failed" in str(exc.value)

    @patch("src.core.transcriber.requests.Session")
    def test_start_transcription_success(self, mock_session_class, transcriber):
        """Test starting transcription."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "test-id-123"}
        mock_session.post.return_value = mock_response
        transcriber.session = mock_session

        transcript_id = transcriber.start_transcription("https://example.com/audio")

        assert transcript_id == "test-id-123"
        mock_session.post.assert_called_once()

    @patch("src.core.transcriber.requests.Session")
    @patch("src.core.transcriber.time.sleep")
    def test_poll_transcription_completed(
        self, mock_sleep, mock_session_class, transcriber, mock_response
    ):
        """Test polling for completed transcription."""
        mock_session = MagicMock()
        mock_api_response = MagicMock()
        mock_api_response.status_code = 200
        mock_api_response.json.return_value = mock_response
        mock_session.get.return_value = mock_api_response
        transcriber.session = mock_session

        result = transcriber.poll_transcription("test-id")

        assert result["status"] == "completed"
        assert result["audio_duration"] == 120

    @patch("src.core.transcriber.requests.Session")
    @patch("src.core.transcriber.time.sleep")
    def test_poll_transcription_error(self, mock_sleep, mock_session_class, transcriber):
        """Test polling handles transcription error."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "error", "error": "Audio too short"}
        mock_session.get.return_value = mock_response
        transcriber.session = mock_session

        with pytest.raises(TranscriptionError) as exc:
            transcriber.poll_transcription("test-id")

        assert "Audio too short" in str(exc.value)

    def test_transcribe_file_not_found(self, transcriber):
        """Test transcribe raises error for missing file."""
        with pytest.raises(TranscriptionError) as exc:
            transcriber.transcribe("/nonexistent/audio.mp4")

        assert "not found" in str(exc.value)

    @patch.object(Transcriber, "upload")
    @patch.object(Transcriber, "start_transcription")
    @patch.object(Transcriber, "poll_transcription")
    def test_transcribe_end_to_end(
        self,
        mock_poll,
        mock_start,
        mock_upload,
        transcriber,
        mock_response,
    ):
        """Test full transcription flow."""
        mock_upload.return_value = "https://example.com/upload"
        mock_start.return_value = "test-id"
        mock_poll.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"test audio content")
            f.flush()

            transcript = transcriber.transcribe(f.name)

            assert transcript.source_file == Path(f.name).name
            assert transcript.duration_seconds == 120
            assert len(transcript.speakers) == 2
            assert len(transcript.utterances) == 3

            Path(f.name).unlink()

    @patch.object(Transcriber, "transcribe")
    def test_transcribe_and_save(self, mock_transcribe, transcriber, mock_response):
        """Test transcribe and save to file."""
        transcript = transcriber.convert_to_transcript_data(mock_response, "/test/audio.mp4")
        mock_transcribe.return_value = transcript

        with tempfile.TemporaryDirectory() as tmpdir:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(b"test")
                f.flush()

                output_path = transcriber.transcribe_and_save(f.name, tmpdir)

                assert output_path.exists()
                assert output_path.suffix == ".yaml"
                assert "transcript" in output_path.name

                content = output_path.read_text()
                assert "source_file:" in content
                assert "utterances:" in content

                Path(f.name).unlink()
