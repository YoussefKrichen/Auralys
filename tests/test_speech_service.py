from pathlib import Path
from types import SimpleNamespace
import uuid

import app.audio.speech_service as speech_service_module
from app.audio.speech_service import SpeechService


class _FakePartFactory:
    @staticmethod
    def from_bytes(*, data, mime_type, media_resolution=None):
        return {
            "data": data,
            "mime_type": mime_type,
            "media_resolution": media_resolution,
        }


class _FakeGenerateContentConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeTypes:
    Part = _FakePartFactory
    GenerateContentConfig = _FakeGenerateContentConfig


class _FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)

        class _Response:
            text = "Bonjour tout le monde"

        return _Response()


class _FakeClient:
    def __init__(self):
        self.models = _FakeModels()


def test_transcribe_uses_gemini_model_and_audio_part(monkeypatch):
    fake_client = _FakeClient()
    service = SpeechService()
    audio_path = Path(".test-work") / f"speech-test-{uuid.uuid4().hex}.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"fake-audio")

    try:
        monkeypatch.setattr(service, "_load_gemini_client", lambda: fake_client)
        monkeypatch.setitem(__import__("sys").modules, "google.genai", type("FakeModule", (), {"types": _FakeTypes})())
        monkeypatch.setattr(
            speech_service_module,
            "settings",
            SimpleNamespace(
                speech_gemini_stt_model="gemini-2.5-flash",
                speech_language="fr",
                google_api_key="test-key",
            ),
        )

        transcript = service.transcribe(audio_path)

        assert transcript == "Bonjour tout le monde"
        assert len(fake_client.models.calls) == 1
        call = fake_client.models.calls[0]
        assert call["model"] == "gemini-2.5-flash"
        assert call["contents"][0].startswith("Transcris cet audio")
        assert call["contents"][1]["mime_type"] == "audio/wav"
        assert call["contents"][1]["data"] == b"fake-audio"
        assert call["config"].kwargs["response_mime_type"] == "text/plain"
        assert "fr" in call["config"].kwargs["system_instruction"]
    finally:
        audio_path.unlink(missing_ok=True)


def test_guess_audio_mime_type_prefers_audio_webm():
    assert SpeechService._guess_audio_mime_type(Path("voice.webm")) == "audio/webm"
