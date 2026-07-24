from unittest.mock import patch

from app.services.transcription_service import TranscribedUtterance, TranscriptionNotConfiguredError


class _FakeProvider:
    def __init__(self, utterances):
        self._utterances = utterances

    def transcribe(self, audio_bytes: bytes):
        return self._utterances


_TWO_SPEAKER_UTTERANCES = [
    TranscribedUtterance(speaker_label="A", start_ms=0, end_ms=1000, text="What brings you in today?", confidence=0.95),
    TranscribedUtterance(speaker_label="B", start_ms=1000, end_ms=5000, text="My chest has hurt for three days.", confidence=0.9),
]


def _seed_encounter(client):
    return client.post("/encounters", json={}).json()


def test_preview_audio_transcript_returns_utterances_and_speaker_labels(client):
    encounter = _seed_encounter(client)

    with patch(
        "app.api.transcripts.get_transcription_provider", return_value=_FakeProvider(_TWO_SPEAKER_UTTERANCES)
    ):
        resp = client.post(
            f"/encounters/{encounter['id']}/transcript/audio/preview",
            files={"file": ("visit.wav", b"fake-audio-bytes", "audio/wav")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["speaker_labels"] == ["A", "B"]
    assert len(body["utterances"]) == 2
    assert body["utterances"][0]["text"] == "What brings you in today?"

    # Nothing persisted yet.
    assert client.get(f"/encounters/{encounter['id']}/transcript").json() == []


def test_preview_audio_transcript_surfaces_missing_api_key_as_503(client):
    encounter = _seed_encounter(client)

    with patch(
        "app.api.transcripts.get_transcription_provider",
        side_effect=TranscriptionNotConfiguredError("no key"),
    ):
        resp = client.post(
            f"/encounters/{encounter['id']}/transcript/audio/preview",
            files={"file": ("visit.wav", b"fake-audio-bytes", "audio/wav")},
        )

    assert resp.status_code == 503


def test_commit_audio_transcript_creates_segments_with_mapped_roles(client):
    encounter = _seed_encounter(client)

    payload = {
        "utterances": [u.model_dump() for u in _TWO_SPEAKER_UTTERANCES],
        "speaker_role_map": {"A": "clinician", "B": "patient"},
    }
    resp = client.post(f"/encounters/{encounter['id']}/transcript/audio/commit", json=payload)

    assert resp.status_code == 201
    segments = resp.json()
    assert len(segments) == 2
    by_label = {s["speaker_identifier"]: s for s in segments}
    assert by_label["assemblyai:A"]["speaker_role"] == "clinician"
    assert by_label["assemblyai:B"]["speaker_role"] == "patient"
    assert by_label["assemblyai:B"]["text"] == "My chest has hurt for three days."

    listed = client.get(f"/encounters/{encounter['id']}/transcript").json()
    assert len(listed) == 2


def test_commit_audio_transcript_rejects_incomplete_role_map(client):
    encounter = _seed_encounter(client)

    payload = {
        "utterances": [u.model_dump() for u in _TWO_SPEAKER_UTTERANCES],
        "speaker_role_map": {"A": "clinician"},  # missing "B"
    }
    resp = client.post(f"/encounters/{encounter['id']}/transcript/audio/commit", json=payload)

    assert resp.status_code == 422
    assert "B" in resp.json()["detail"]
    assert client.get(f"/encounters/{encounter['id']}/transcript").json() == []
