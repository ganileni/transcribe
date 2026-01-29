"""AssemblyAI transcription client."""

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests

from ..models import Speaker, TranscriptData, Utterance


class TranscriptionError(Exception):
    """Error during transcription."""

    pass


class Transcriber:
    """AssemblyAI transcription client with speaker diarization."""

    BASE_URL = "https://api.assemblyai.com/v2"

    def __init__(self, api_key: str):
        """Initialize the transcriber.

        Args:
            api_key: AssemblyAI API key.
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"Authorization": api_key})

    def upload(self, audio_path: str | Path, progress_callback: Callable[[str], None] | None = None) -> str:
        """Upload an audio file to AssemblyAI.

        Args:
            audio_path: Path to the audio file.
            progress_callback: Optional callback for progress updates.

        Returns:
            The upload URL.

        Raises:
            TranscriptionError: If upload fails.
        """
        if progress_callback:
            progress_callback("Uploading audio file...")

        with open(audio_path, "rb") as f:
            response = self.session.post(
                f"{self.BASE_URL}/upload",
                headers={"Content-Type": "application/octet-stream"},
                data=f,
            )

        if response.status_code != 200:
            raise TranscriptionError(f"Upload failed: {response.text}")

        data = response.json()
        upload_url = data.get("upload_url")
        if not upload_url:
            raise TranscriptionError(f"No upload URL in response: {data}")

        return upload_url

    def start_transcription(
        self, upload_url: str, progress_callback: Callable[[str], None] | None = None
    ) -> str:
        """Start a transcription job.

        Args:
            upload_url: The URL of the uploaded audio.
            progress_callback: Optional callback for progress updates.

        Returns:
            The transcript ID.

        Raises:
            TranscriptionError: If starting transcription fails.
        """
        if progress_callback:
            progress_callback("Starting transcription with speaker diarization...")

        response = self.session.post(
            f"{self.BASE_URL}/transcript",
            json={"audio_url": upload_url, "speaker_labels": True},
        )

        if response.status_code != 200:
            raise TranscriptionError(f"Failed to start transcription: {response.text}")

        data = response.json()
        transcript_id = data.get("id")
        if not transcript_id:
            raise TranscriptionError(f"No transcript ID in response: {data}")

        return transcript_id

    def poll_transcription(
        self,
        transcript_id: str,
        progress_callback: Callable[[str], None] | None = None,
        poll_interval: float = 5.0,
    ) -> dict[str, Any]:
        """Poll for transcription completion.

        Args:
            transcript_id: The transcript ID to poll.
            progress_callback: Optional callback for progress updates.
            poll_interval: Seconds between polling attempts.

        Returns:
            The completed transcription response.

        Raises:
            TranscriptionError: If transcription fails.
        """
        if progress_callback:
            progress_callback("Waiting for transcription to complete...")

        while True:
            response = self.session.get(f"{self.BASE_URL}/transcript/{transcript_id}")

            if response.status_code != 200:
                raise TranscriptionError(f"Failed to poll transcription: {response.text}")

            data = response.json()
            status = data.get("status")

            if status == "completed":
                return data
            elif status == "error":
                error = data.get("error", "Unknown error")
                raise TranscriptionError(f"Transcription error: {error}")
            else:
                if progress_callback:
                    progress_callback(f"Status: {status}")
                time.sleep(poll_interval)

    def convert_to_transcript_data(
        self, response: dict[str, Any], source_file: str | Path
    ) -> TranscriptData:
        """Convert AssemblyAI response to TranscriptData.

        Args:
            response: The AssemblyAI transcription response.
            source_file: The original audio file path.

        Returns:
            TranscriptData object.
        """
        duration = response.get("audio_duration", 0)
        utterances_data = response.get("utterances", [])

        # Get unique speakers
        speaker_ids = sorted(set(u["speaker"] for u in utterances_data))
        speakers = [Speaker(id=sid) for sid in speaker_ids]

        # Convert utterances (times are in milliseconds)
        utterances = [
            Utterance(
                speaker=u["speaker"],
                start=u["start"] / 1000.0,
                end=u["end"] / 1000.0,
                text=u["text"],
            )
            for u in utterances_data
        ]

        return TranscriptData(
            source_file=Path(source_file).name,
            transcribed=datetime.now(),
            duration_seconds=int(duration),
            labeled=False,
            speakers=speakers,
            utterances=utterances,
        )

    def transcribe(
        self,
        audio_path: str | Path,
        progress_callback: Callable[[str], None] | None = None,
    ) -> TranscriptData:
        """Transcribe an audio file end-to-end.

        Args:
            audio_path: Path to the audio file.
            progress_callback: Optional callback for progress updates.

        Returns:
            TranscriptData with the transcription.

        Raises:
            TranscriptionError: If any step fails.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        upload_url = self.upload(audio_path, progress_callback)
        transcript_id = self.start_transcription(upload_url, progress_callback)
        response = self.poll_transcription(transcript_id, progress_callback)

        return self.convert_to_transcript_data(response, audio_path)

    def transcribe_and_save(
        self,
        audio_path: str | Path,
        output_dir: str | Path,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Path:
        """Transcribe an audio file and save the result.

        Args:
            audio_path: Path to the audio file.
            output_dir: Directory to save the transcript.
            progress_callback: Optional callback for progress updates.

        Returns:
            Path to the saved transcript file.
        """
        audio_path = Path(audio_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate output filename
        basename = audio_path.stem
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
        output_file = output_dir / f"{timestamp}-{basename}-transcript.yaml"

        transcript = self.transcribe(audio_path, progress_callback)
        transcript.save(output_file)

        if progress_callback:
            progress_callback(f"Transcription saved to: {output_file}")

        return output_file
