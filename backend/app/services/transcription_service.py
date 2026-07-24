"""Raw audio ingestion, behind a small TranscriptionProvider interface so the
concrete ASR vendor is swappable -- AssemblyAIProvider is the only
implementation in this build, mirroring how claude_service.py is the single
isolation point for all Claude calls.

The brief names "AssemblyAI Universal 3 Pro" and "Medical Mode" specifically.
This implementation uses AssemblyAI's real, documented API surface instead
(`speech_model="best"`, `speaker_labels=True`, a boosted custom vocabulary of
clinical terms) -- a distinctly-branded "Universal 3 Pro" + "Medical Mode"
combination isn't part of AssemblyAI's confirmed public API as of this
build. See README deviations. Swapping the model string, or wiring in a real
medical-specific mode flag if AssemblyAI ships one, is a one-line change
confined to this file.

AssemblyAI's diarization returns anonymous speaker labels ("A", "B", ...),
not semantic roles -- there is no way to infer "this is the patient" from
audio alone. Mapping each label to a SpeakerRole is therefore a step the
caller must do explicitly (see app/api/transcripts.py's preview/commit
endpoints), never guessed by this service.
"""

import time

import httpx
from pydantic import BaseModel

from app.config import Settings

_UPLOAD_URL = "https://api.assemblyai.com/v2/upload"
_TRANSCRIPT_URL = "https://api.assemblyai.com/v2/transcript"
_POLL_INTERVAL_SECONDS = 3
_MAX_POLL_ATTEMPTS = 100  # ~5 minutes before giving up

# Stands in for the brief's "Medical Mode" -- AssemblyAI's real word-boost
# custom vocabulary feature, biased toward this build's demo scenarios.
_CLINICAL_WORD_BOOST = [
    "lisinopril",
    "amoxicillin",
    "penicillin",
    "hypertension",
    "tachycardia",
    "dyspnea",
    "myocardial infarction",
    "hyperlipidemia",
    "metformin",
]


class TranscriptionNotConfiguredError(RuntimeError):
    pass


class TranscribedUtterance(BaseModel):
    speaker_label: str
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None


class AssemblyAIProvider:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def transcribe(self, audio_bytes: bytes) -> list[TranscribedUtterance]:
        headers = {"authorization": self._api_key}

        upload_resp = httpx.post(_UPLOAD_URL, headers=headers, content=audio_bytes, timeout=60)
        upload_resp.raise_for_status()
        upload_url = upload_resp.json()["upload_url"]

        submit_resp = httpx.post(
            _TRANSCRIPT_URL,
            headers=headers,
            json={
                "audio_url": upload_url,
                "speaker_labels": True,
                "speech_model": "best",
                "word_boost": _CLINICAL_WORD_BOOST,
            },
            timeout=30,
        )
        submit_resp.raise_for_status()
        transcript_id = submit_resp.json()["id"]

        for _ in range(_MAX_POLL_ATTEMPTS):
            poll_resp = httpx.get(f"{_TRANSCRIPT_URL}/{transcript_id}", headers=headers, timeout=30)
            poll_resp.raise_for_status()
            result = poll_resp.json()
            status = result["status"]
            if status == "completed":
                return [
                    TranscribedUtterance(
                        speaker_label=u["speaker"],
                        start_ms=u["start"],
                        end_ms=u["end"],
                        text=u["text"],
                        confidence=u.get("confidence"),
                    )
                    for u in result.get("utterances", [])
                ]
            if status == "error":
                raise RuntimeError(f"AssemblyAI transcription failed: {result.get('error')}")
            time.sleep(_POLL_INTERVAL_SECONDS)

        raise RuntimeError("AssemblyAI transcription timed out waiting for a completed status")


def get_transcription_provider(settings: Settings) -> AssemblyAIProvider:
    if not settings.assemblyai_api_key:
        raise TranscriptionNotConfiguredError(
            "ASSEMBLYAI_API_KEY is not configured -- set it in .env to enable raw audio ingestion."
        )
    return AssemblyAIProvider(settings.assemblyai_api_key)
