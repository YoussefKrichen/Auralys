from __future__ import annotations

import json
import mimetypes
import re
import tempfile
import wave
from pathlib import Path
from typing import Any

from app.config import settings


class SpeechService:
    def __init__(self) -> None:
        self._piper_voice = None
        self._piper_voice_info = None
        self._gemini_client = None

    def list_voices(self) -> list[dict[str, str]]:
        if settings.speech_tts_backend == "gemini":
            return [self._get_gemini_voice_info()]
        if settings.speech_tts_backend == "piper":
            return [self._get_piper_voice_info()]
        engine = self._build_tts_engine()
        try:
            voices = []
            for voice in engine.getProperty("voices"):
                voices.append(
                    {
                        "id": str(getattr(voice, "id", "")),
                        "name": str(getattr(voice, "name", "")),
                        "gender": str(getattr(voice, "gender", "")),
                        "languages": str(getattr(voice, "languages", "")),
                    }
                )
            return voices
        finally:
            engine.stop()

    def transcribe(self, input_path: str | Path) -> str:
        path = Path(input_path)
        text = self._transcribe_with_gemini(path)
        if not text:
            raise RuntimeError(f"No transcription text was returned for `{path}`.")
        return text

    def synthesize(self, text: str, output_path: str | Path) -> Path:
        if settings.speech_tts_backend == "gemini":
            return self._synthesize_with_gemini(text, output_path)
        if settings.speech_tts_backend == "piper":
            return self._synthesize_with_piper(text, output_path)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = self._build_tts_engine()
        engine.save_to_file(self._prepare_tts_text(text), str(path))
        engine.runAndWait()
        engine.stop()
        return path

    def speak_text(self, text: str) -> None:
        if settings.speech_tts_backend == "gemini":
            self._speak_with_gemini(text)
            return
        if settings.speech_tts_backend == "piper":
            self._speak_with_piper(text)
            return
        engine = self._build_tts_engine()
        engine.say(self._prepare_tts_text(text))
        engine.runAndWait()
        engine.stop()

    def record_microphone(
        self,
        output_path: str | Path,
        duration_seconds: float | None = None,
        sample_rate: int | None = None,
        channels: int | None = None,
    ) -> Path:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Real-time voice capture requires `sounddevice` and `numpy`."
            ) from exc

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = sample_rate or settings.speech_input_sample_rate
        channels = channels or settings.speech_input_channels
        max_duration_seconds = duration_seconds or settings.speech_live_max_turn_seconds
        audio = self._record_until_silence(
            sample_rate=sample_rate,
            channels=channels,
            max_duration_seconds=max_duration_seconds,
        )
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio.tobytes())
        return path

    def _record_until_silence(
        self,
        sample_rate: int,
        channels: int,
        max_duration_seconds: float,
    ) -> Any:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Real-time voice capture requires `sounddevice` and `numpy`."
            ) from exc

        chunk_seconds = max(settings.speech_audio_chunk_seconds, 0.05)
        chunk_frames = max(1, int(sample_rate * chunk_seconds))
        silence_limit_seconds = max(settings.speech_silence_stop_seconds, 0.5)
        activation_threshold = max(settings.speech_voice_activation_threshold, 0.001)
        max_frames = max(chunk_frames, int(sample_rate * max_duration_seconds))

        chunks: list[np.ndarray] = []
        speech_started = False
        trailing_silence_seconds = 0.0
        recorded_frames = 0

        with sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            blocksize=chunk_frames,
        ) as stream:
            while recorded_frames < max_frames:
                audio_chunk, _ = stream.read(chunk_frames)
                chunk_array = np.asarray(audio_chunk, dtype=np.int16)
                chunks.append(chunk_array.copy())
                recorded_frames += len(chunk_array)

                normalized = chunk_array.astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(np.square(normalized)))) if normalized.size else 0.0
                chunk_duration_seconds = len(chunk_array) / sample_rate

                if rms >= activation_threshold:
                    speech_started = True
                    trailing_silence_seconds = 0.0
                    continue

                if speech_started:
                    trailing_silence_seconds += chunk_duration_seconds
                    if trailing_silence_seconds >= silence_limit_seconds:
                        break

        if not chunks:
            raise RuntimeError("Aucun audio n'a ete capture depuis le microphone.")

        audio = np.concatenate(chunks, axis=0)
        if not speech_started:
            return audio

        trim_frames = int(trailing_silence_seconds * sample_rate)
        if trim_frames > 0 and trim_frames < len(audio):
            audio = audio[:-trim_frames]
        return audio

    def live_turn(
        self,
        answer_service: Any,
        duration_seconds: float | None = None,
        keep_audio_file: bool = False,
        output_audio_path: str | Path | None = None,
    ) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            temp_path = Path(handle.name)
        self.record_microphone(temp_path, duration_seconds=duration_seconds)
        try:
            try:
                transcript = self.transcribe(temp_path)
            except RuntimeError as exc:
                if "No transcription text was returned" not in str(exc):
                    raise
                prompt_text = "Je n'ai pas bien entendu. Merci de reessayer plus pres du microphone."
                self.speak_text(prompt_text)
                saved_output_audio_path = None
                if output_audio_path is not None:
                    saved_output_audio_path = str(self.synthesize(prompt_text, output_audio_path))
                return {
                    "input_type": "voice",
                    "transcript": "",
                    "answer": prompt_text,
                    "spoken_text": prompt_text,
                    "intent": "no_transcription",
                    "hits": [],
                    "sav_admin_analysis": {},
                    "admin_alert": None,
                    "input_audio_path": str(temp_path) if keep_audio_file else None,
                    "output_audio_path": saved_output_audio_path,
                    "wake_word_detected": not settings.speech_wake_word_enabled,
                    "wake_word_transcript": "",
                }
            activation = self._extract_wake_word_query(transcript)
            if activation is None:
                return {
                    "input_type": "voice",
                    "transcript": transcript,
                    "answer": "",
                    "spoken_text": None,
                    "intent": "wake_word_not_detected",
                    "hits": [],
                    "sav_admin_analysis": {},
                    "admin_alert": None,
                    "input_audio_path": str(temp_path) if keep_audio_file else None,
                    "output_audio_path": None,
                    "wake_word_detected": False,
                    "wake_word_transcript": transcript,
                }
            cleaned_query = activation
            if not cleaned_query:
                prompt_text = "Je vous ecoute."
                self.speak_text(prompt_text)
                saved_output_audio_path = None
                if output_audio_path is not None:
                    saved_output_audio_path = str(self.synthesize(prompt_text, output_audio_path))
                return {
                    "input_type": "voice",
                    "transcript": transcript,
                    "answer": prompt_text,
                    "spoken_text": prompt_text,
                    "intent": "wake_word_detected",
                    "hits": [],
                    "sav_admin_analysis": {},
                    "admin_alert": None,
                    "input_audio_path": str(temp_path) if keep_audio_file else None,
                    "output_audio_path": saved_output_audio_path,
                    "wake_word_detected": True,
                    "wake_word_transcript": "",
                }
            result = answer_service.answer(cleaned_query)
            spoken_text = result.get("spoken_text") or result["answer"]
            self.speak_text(spoken_text)
            saved_output_audio_path = None
            if output_audio_path is not None:
                saved_output_audio_path = str(self.synthesize(spoken_text, output_audio_path))
            return {
                "input_type": "voice",
                "transcript": transcript,
                "answer": result["answer"],
                "spoken_text": spoken_text,
                "intent": result["intent"],
                "hits": result["hits"],
                "sav_admin_analysis": result.get("sav_admin_analysis", {}),
                "admin_alert": result.get("admin_alert"),
                "input_audio_path": str(temp_path) if keep_audio_file else None,
                "output_audio_path": saved_output_audio_path,
                "wake_word_detected": True,
                "wake_word_transcript": cleaned_query,
            }
        finally:
            if not keep_audio_file and temp_path.exists():
                temp_path.unlink()

    def answer_from_audio(
        self,
        input_path: str | Path,
        output_path: str | Path | None,
        answer_service,
    ) -> dict:
        try:
            transcript = self.transcribe(input_path)
        except RuntimeError as exc:
            if "No transcription text was returned" not in str(exc):
                raise
            prompt_text = "Je n'ai pas bien entendu. Merci de renvoyer un message vocal plus clair."
            audio_output_path = None
            if output_path is not None:
                audio_output_path = str(self.synthesize(prompt_text, output_path))
            return {
                "input_audio_path": str(Path(input_path)),
                "transcript": "",
                "answer": prompt_text,
                "spoken_text": prompt_text,
                "intent": "no_transcription",
                "hits": [],
                "output_audio_path": audio_output_path,
                "wake_word_detected": not settings.speech_wake_word_enabled,
                "wake_word_transcript": "",
            }
        activation = self._extract_wake_word_query(transcript)
        if activation is None:
            return {
                "input_audio_path": str(Path(input_path)),
                "transcript": transcript,
                "answer": "",
                "spoken_text": None,
                "intent": "wake_word_not_detected",
                "hits": [],
                "output_audio_path": None,
                "wake_word_detected": False,
                "wake_word_transcript": transcript,
            }
        if not activation:
            prompt_text = "Je vous ecoute."
            audio_output_path = None
            if output_path is not None:
                audio_output_path = str(self.synthesize(prompt_text, output_path))
            return {
                "input_audio_path": str(Path(input_path)),
                "transcript": transcript,
                "answer": prompt_text,
                "spoken_text": prompt_text,
                "intent": "wake_word_detected",
                "hits": [],
                "output_audio_path": audio_output_path,
                "wake_word_detected": True,
                "wake_word_transcript": "",
            }
        result = answer_service.answer(activation)
        audio_output_path = None
        if output_path is not None:
            audio_output_path = str(self.synthesize(result.get("spoken_text") or result["answer"], output_path))
        return {
            "input_audio_path": str(Path(input_path)),
            "transcript": transcript,
            "answer": result["answer"],
            "spoken_text": result.get("spoken_text"),
            "intent": result["intent"],
            "hits": result["hits"],
            "output_audio_path": audio_output_path,
            "wake_word_detected": True,
            "wake_word_transcript": activation,
        }

    def _transcribe_with_gemini(self, input_path: Path) -> str:
        client = self._load_gemini_client()
        try:
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Le backend Gemini requiert `google-genai`. Installe-le avec `pip install -r requirements.txt`."
            ) from exc

        language = (settings.speech_language or "").strip()
        config = types.GenerateContentConfig(
            temperature=0,
            response_mime_type="text/plain",
            system_instruction=(
                (
                    f"Transcris l'audio en priorite en {language}. "
                    "N'ajoute aucun commentaire et ne traduis pas."
                )
                if language
                else "Transcris l'audio dans sa langue detectee. N'ajoute aucun commentaire et ne traduis pas."
            ),
        )
        try:
            response = client.models.generate_content(
                model=settings.speech_gemini_stt_model,
                contents=[
                    self._build_gemini_stt_prompt(),
                    types.Part.from_bytes(
                        data=input_path.read_bytes(),
                        mime_type=self._guess_audio_mime_type(input_path),
                    ),
                ],
                config=config,
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini STT request failed: {exc}") from exc

        text = self._extract_gemini_text_response(response).strip()
        if not text:
            raise RuntimeError(f"Gemini STT returned no text for `{input_path}`.")
        return text

    def _build_tts_engine(self):
        try:
            import pyttsx3
        except ImportError as exc:
            raise RuntimeError(
                "pyttsx3 is not installed. Run `pip install -r requirements.txt`."
            ) from exc
        engine = pyttsx3.init()
        engine.setProperty("rate", settings.speech_tts_rate)
        engine.setProperty("volume", settings.speech_tts_volume)
        voices = engine.getProperty("voices")
        if settings.speech_tts_voice:
            explicit_voice = self._find_voice_by_name_or_id(voices, settings.speech_tts_voice)
            if explicit_voice:
                engine.setProperty("voice", explicit_voice)
                return engine
            for voice in voices:
                if settings.speech_tts_voice in {getattr(voice, "id", ""), getattr(voice, "name", "")}:
                    engine.setProperty("voice", voice.id)
                    break
        else:
            preferred_voice_id = self._select_preferred_voice(voices)
            if preferred_voice_id:
                engine.setProperty("voice", preferred_voice_id)
        return engine

    def _select_preferred_voice(self, voices) -> str | None:
        preferred_language = settings.speech_tts_language_preference.lower()
        preferred_gender = settings.speech_tts_gender_preference.lower()
        french_tokens = (
            "fr",
            "fr-",
            "fr_",
            "french",
            "francais",
            "français",
            "france",
            "belg",
            "canad",
            "helene",
            "hortense",
            "julie",
            "sophie",
            "harmonie",
            "juliette",
            "amelie",
            "audrey",
            "fr-fr",
        )
        female_tokens = ("female", "femme", "zira", "hazel", "helene", "hortense", "julie", "sophie")
        male_tokens = ("male", "homme", "david", "paul", "george")
        if preferred_gender == "female":
            target_tokens = female_tokens
        elif preferred_gender == "male":
            target_tokens = male_tokens
        else:
            target_tokens = ()

        ranked_voices: list[tuple[int, str]] = []
        for voice in voices:
            searchable = self._voice_searchable_text(voice)
            score = 0
            preferred_alias_score = self._score_preferred_voice_alias(searchable)
            score += preferred_alias_score
            if preferred_language.startswith("fr") and any(token in searchable for token in french_tokens):
                score += 6
            if any(token in searchable for token in target_tokens):
                score += 3
            if "desktop" in searchable:
                score += 2
            if "natural" in searchable:
                score += 2
            if "harm" in searchable or "premium" in searchable:
                score += 1
            voice_id = getattr(voice, "id", None)
            if voice_id and score > 0:
                ranked_voices.append((score, voice_id))

        if ranked_voices:
            ranked_voices.sort(key=lambda item: item[0], reverse=True)
            return ranked_voices[0][1]
        return None

    def _load_piper_voice(self):
        if self._piper_voice is not None:
            return self._piper_voice
        model_path = settings.speech_piper_model_path
        if not model_path:
            raise RuntimeError(
                "Piper est selectionne comme backend TTS, mais `SPEECH_PIPER_MODEL_PATH` n'est pas configure."
            )
        model_file = Path(model_path)
        if not model_file.exists():
            raise RuntimeError(f"Le modele Piper est introuvable: `{model_file}`.")
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise RuntimeError(
                "Le backend Piper requiert `piper-tts`. Installe-le avec `pip install piper-tts`."
            ) from exc
        if settings.speech_piper_config_path:
            config_path = Path(settings.speech_piper_config_path)
            if not config_path.exists():
                raise RuntimeError(f"Le fichier de configuration Piper est introuvable: `{config_path}`.")
        self._piper_voice = PiperVoice.load(str(model_file), use_cuda=settings.speech_piper_use_cuda)
        return self._piper_voice

    def _load_gemini_client(self):
        if self._gemini_client is not None:
            return self._gemini_client
        if not settings.google_api_key:
            raise RuntimeError(
                "Gemini est requis pour la voix, mais `GOOGLE_API_KEY` n'est pas configure."
            )
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "Le backend Gemini requiert `google-genai`. Installe-le avec `pip install -r requirements.txt`."
            ) from exc
        self._gemini_client = genai.Client(api_key=settings.google_api_key)
        return self._gemini_client

    def _synthesize_with_gemini(self, text: str, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        pcm_data = self._generate_gemini_pcm(text)
        self._write_wave_file(
            path,
            pcm_data,
            channels=settings.speech_gemini_tts_channels,
            rate=settings.speech_gemini_tts_sample_rate,
            sample_width=settings.speech_gemini_tts_sample_width,
        )
        return path

    def _speak_with_gemini(self, text: str) -> None:
        try:
            import winsound
        except ImportError as exc:
            raise RuntimeError("La lecture audio Gemini en direct n'est pas disponible sur cette plateforme.") from exc
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            self._synthesize_with_gemini(text, temp_path)
            winsound.PlaySound(str(temp_path), winsound.SND_FILENAME)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _generate_gemini_pcm(self, text: str) -> bytes:
        client = self._load_gemini_client()
        try:
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Le backend Gemini requiert `google-genai`. Installe-le avec `pip install -r requirements.txt`."
            ) from exc

        prompt = self._build_gemini_tts_prompt(text)
        response = client.models.generate_content(
            model=settings.speech_gemini_tts_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=settings.speech_gemini_tts_voice
                        )
                    )
                ),
            ),
        )

        try:
            return bytes(response.candidates[0].content.parts[0].inline_data.data)
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise RuntimeError("La reponse Gemini TTS ne contient pas de donnees audio exploitables.") from exc

    def _synthesize_with_piper(self, text: str, output_path: str | Path) -> Path:
        voice = self._load_piper_voice()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        prepared_text = self._prepare_tts_text(text)
        with wave.open(str(path), "wb") as wav_file:
            voice.synthesize_wav(
                prepared_text,
                wav_file,
                syn_config=self._build_piper_synthesis_config(),
            )
        return path

    def _speak_with_piper(self, text: str) -> None:
        try:
            import winsound
        except ImportError as exc:
            raise RuntimeError("La lecture audio Piper en direct n'est pas disponible sur cette plateforme.") from exc
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            self._synthesize_with_piper(text, temp_path)
            winsound.PlaySound(str(temp_path), winsound.SND_FILENAME)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _build_piper_synthesis_config(self):
        try:
            from piper import SynthesisConfig
        except ImportError as exc:
            raise RuntimeError(
                "Le backend Piper requiert `piper-tts`. Installe-le avec `pip install piper-tts`."
            ) from exc
        return SynthesisConfig(
            volume=settings.speech_tts_volume,
            speaker_id=settings.speech_piper_speaker,
            noise_scale=settings.speech_piper_noise_scale,
            noise_w_scale=settings.speech_piper_noise_w_scale,
            length_scale=settings.speech_piper_length_scale,
            normalize_audio=settings.speech_piper_normalize_audio,
        )

    def _get_piper_voice_info(self) -> dict[str, str]:
        if self._piper_voice_info is not None:
            return self._piper_voice_info
        model_path = settings.speech_piper_model_path
        if not model_path:
            return {
                "backend": "piper",
                "id": "",
                "name": "Piper non configure",
                "gender": "",
                "languages": "",
            }
        config_path = Path(settings.speech_piper_config_path) if settings.speech_piper_config_path else Path(
            f"{model_path}.json"
        )
        metadata: dict[str, Any] = {}
        if config_path.exists():
            metadata = json.loads(config_path.read_text(encoding="utf-8"))
        language = metadata.get("language", {})
        speaker_count = metadata.get("num_speakers")
        self._piper_voice_info = {
            "backend": "piper",
            "id": str(model_path),
            "name": Path(model_path).stem,
            "gender": str(metadata.get("speaker") or ""),
            "languages": str(language.get("code") or language.get("name") or ""),
            "speakers": "" if speaker_count in (None, "") else str(speaker_count),
        }
        return self._piper_voice_info

    def _get_gemini_voice_info(self) -> dict[str, str]:
        return {
            "backend": "gemini",
            "id": settings.speech_gemini_tts_voice,
            "name": settings.speech_gemini_tts_voice,
            "gender": "",
            "languages": settings.speech_language or "fr",
            "model": settings.speech_gemini_tts_model,
        }

    @staticmethod
    def _voice_searchable_text(voice: Any) -> str:
        return " ".join(
            str(value).lower()
            for value in (
                getattr(voice, "id", ""),
                getattr(voice, "name", ""),
                getattr(voice, "gender", ""),
                getattr(voice, "languages", ""),
                getattr(voice, "age", ""),
            )
        )

    def _score_preferred_voice_alias(self, searchable: str) -> int:
        for index, alias in enumerate(settings.speech_tts_preferred_voices):
            normalized_alias = alias.strip().lower()
            if normalized_alias and normalized_alias in searchable:
                return max(12 - index, 4)
        return 0

    def _find_voice_by_name_or_id(self, voices, expected: str) -> str | None:
        normalized_expected = expected.strip().lower()
        for voice in voices:
            searchable = self._voice_searchable_text(voice)
            if normalized_expected and normalized_expected in searchable:
                voice_id = getattr(voice, "id", None)
                if voice_id:
                    return str(voice_id)
        return None

    @staticmethod
    def _prepare_tts_text(text: str) -> str:
        normalized = text.strip()
        if not normalized:
            return ""
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"\bAuralys\b", "Ora-liss", normalized, flags=re.IGNORECASE)
        normalized = normalized.replace(" : ", ", ")
        normalized = normalized.replace(" ; ", ". ")
        normalized = re.sub(r"\bSAV\b", "S. A. V.", normalized)
        normalized = re.sub(r"\badmin\b", "administration", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bml\b", "millilitres", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\betc\.\b", "et cetera", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"([.!?])\s*", r"\1 ", normalized)
        normalized = re.sub(r",\s*", ", ", normalized)
        return normalized.strip()

    def _build_gemini_tts_prompt(self, text: str) -> str:
        prepared_text = self._prepare_tts_text(text)
        instruction = settings.speech_gemini_tts_instruction.strip()
        if not instruction:
            return prepared_text
        if instruction.endswith((":", ".", "!", "?")):
            return f"{instruction} {prepared_text}"
        return f"{instruction}: {prepared_text}"

    @staticmethod
    def _build_gemini_stt_prompt() -> str:
        return (
            "Transcris cet audio mot a mot de la facon la plus fidele possible. "
            "Retourne uniquement la transcription finale, sans resume, sans annotation, sans horodatage et sans traduction."
        )

    @staticmethod
    def _extract_gemini_text_response(response: Any) -> str:
        text = getattr(response, "text", None)
        if text and str(text).strip():
            return str(text).strip()

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            text_parts: list[str] = []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    text_parts.append(str(part_text))
            if text_parts:
                return "".join(text_parts).strip()
        return ""

    @staticmethod
    def _guess_audio_mime_type(input_path: Path) -> str:
        if input_path.suffix.lower() == ".webm":
            return "audio/webm"
        guessed_type, _ = mimetypes.guess_type(str(input_path))
        if guessed_type and guessed_type.startswith("audio/"):
            return guessed_type
        return "audio/wav"

    @staticmethod
    def _write_wave_file(
        output_path: str | Path,
        pcm_data: bytes,
        channels: int,
        rate: int,
        sample_width: int,
    ) -> None:
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(rate)
            wav_file.writeframes(pcm_data)

    def _extract_wake_word_query(self, transcript: str) -> str | None:
        cleaned_transcript = transcript.strip()
        if not cleaned_transcript:
            return None
        if not settings.speech_wake_word_enabled:
            return cleaned_transcript
        normalized = self._normalize_trigger_text(cleaned_transcript)
        for variant in settings.speech_wake_word_variants:
            normalized_variant = self._normalize_trigger_text(variant)
            if not normalized_variant:
                continue
            match = re.search(rf"\b{re.escape(normalized_variant)}\b", normalized)
            if not match:
                continue
            remainder = normalized[:match.start()] + " " + normalized[match.end():]
            remainder = re.sub(r"\s+", " ", remainder).strip(" ,.!?-")
            remainder = re.sub(
                r"^(bonjour|bonsoir|salut|s il te plait|stp|hey|coucou)\s+",
                "",
                remainder,
            ).strip()
            return remainder
        return None

    @staticmethod
    def _normalize_trigger_text(text: str) -> str:
        normalized = text.lower()
        normalized = normalized.replace("au", "o")
        normalized = normalized.replace("ora-", "ora ")
        normalized = normalized.replace("-", " ")
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()
