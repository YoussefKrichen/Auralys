from __future__ import annotations

import json
import base64
from typing import Any
from urllib import error, request

from app.config import settings
from schemas.agent_schema import ImageAttachment


class LLMService:
    def __init__(self) -> None:
        self._provider = settings.llm_provider
        self._enabled = self._is_provider_enabled()

    def generate_text(self, prompt: str) -> str:
        if not self._enabled:
            raise RuntimeError(self._disabled_reason())
        return self._remote_answer(prompt)

    def answer(self, prompt: str, fallback_context: str, query: str = "", analysis: Any | None = None) -> str:
        return self.answer_details(prompt, fallback_context, query=query, analysis=analysis)["answer"]

    def describe_images(self, prompt: str, images: list[ImageAttachment]) -> list[str]:
        if not images:
            return []
        if self._provider != "gemini":
            return [f"Image jointe recue: {image.name} ({image.media_type})." for image in images]
        if not self._enabled:
            return [f"Image jointe recue: {image.name} ({image.media_type})." for image in images]
        try:
            return self._gemini_describe_images(prompt, images)
        except RuntimeError:
            return [f"Image jointe recue: {image.name} ({image.media_type})." for image in images]

    def answer_details(
        self,
        prompt: str,
        fallback_context: str,
        query: str = "",
        analysis: Any | None = None,
    ) -> dict[str, str | None]:
        if not self._enabled:
            fallback = self._fallback_answer(fallback_context, query, analysis)
            return {
                "answer": fallback,
                "response_source": "fallback",
                "model_output": None,
                "llm_error": self._disabled_reason(),
            }
        try:
            model_output = self.generate_text(prompt)
            return {
                "answer": model_output.strip(),
                "response_source": self._provider,
                "model_output": model_output,
                "llm_error": None,
            }
        except RuntimeError as exc:
            fallback = self._fallback_answer(fallback_context, query, analysis)
            return {
                "answer": fallback,
                "response_source": "fallback",
                "model_output": None,
                "llm_error": str(exc),
            }

    @staticmethod
    def _fallback_answer(fallback_context: str, query: str, analysis: Any | None) -> str:
        lowered = query.lower()
        matched_products = _read_analysis_list(analysis, "matched_products")
        missing_information = _read_analysis_list(analysis, "missing_information")
        if "fuite" in lowered:
            return (
                "Je recommande de securiser d'abord l'appareil et d'en suspendre l'utilisation si necessaire. "
                "Il faut ensuite verifier l'etancheite, l'etat de la bouteille et la zone de fuite avant de choisir entre une reparation, un echange ou un suivi technique."
            )
        if "trop faible" in lowered or "mal diffuse" in lowered:
            return (
                "Je recommande de verifier en priorite le niveau de parfum, la frequence de diffusion, la plage horaire et l'adequation du modele a la surface. "
                "Si ces points sont conformes, il faut ensuite controler l'etat du diffuseur."
            )
        if "avant validation" in lowered or "quels points l'administration doit verifier" in lowered:
            return (
                "L'administration doit verifier la surface a couvrir, le type de lieu, le budget, le delai, l'historique du client, "
                "le cout de l'intervention ainsi que le besoin eventuel d'une escalade interne ou d'un devis."
            )
        if matched_products:
            recommendation = ", puis ".join(matched_products[:2])
            details = ""
            if missing_information:
                details = " Les points a confirmer sont : " + ", ".join(missing_information[:3]) + "."
            return f"Je recommande en priorite {recommendation}.{details}"
        if not fallback_context.strip():
            return (
                "Je ne dispose pas encore d'assez de contexte produit verifie pour faire une recommandation fiable. "
                "Merci de partager le type de lieu, la surface a couvrir, votre delai et l'objectif de la demande."
            )
        first_block = fallback_context.split("\n\n", 1)[0]
        return (
            "Le meilleur element retrouve dans le contexte disponible est le suivant : "
            f"{first_block} "
            "Merci de confirmer la surface, le type de lieu, le delai et les points a verifier pour affiner la recommandation."
        )

    def _is_provider_enabled(self) -> bool:
        if self._provider == "gemini":
            return bool(settings.google_api_key)
        if self._provider == "groq":
            return bool(settings.groq_api_key)
        return False

    def _disabled_reason(self) -> str:
        if self._provider == "gemini":
            return "GOOGLE_API_KEY is not configured."
        if self._provider == "groq":
            return "GROQ_API_KEY is not configured."
        return f"Unsupported LLM provider `{self._provider}`."

    def _remote_answer(self, prompt: str) -> str:
        if self._provider == "gemini":
            return self._gemini_answer(prompt)
        if self._provider == "groq":
            return self._groq_answer(prompt)
        raise RuntimeError(f"Unsupported LLM provider `{self._provider}`.")

    def _groq_answer(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": settings.groq_chat_model,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        base_url = settings.groq_base_url.rstrip("/")
        req = request.Request(
            url=f"{base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Auralys/1.0",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Groq request failed with status {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Groq request failed: {exc.reason}") from exc
        message = body["choices"][0]["message"]["content"]
        if isinstance(message, list):
            text_parts = [item.get("text", "") for item in message if isinstance(item, dict)]
            return "".join(text_parts).strip()
        return str(message).strip()

    def _gemini_answer(self, prompt: str) -> str:
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "Gemini LLM requires `google-genai`. Run `pip install -r requirements.txt`."
            ) from exc

        try:
            client = genai.Client(api_key=settings.google_api_key)
            response = client.models.generate_content(
                model=settings.gemini_chat_model,
                contents=prompt,
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini request failed: {exc}") from exc

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
        raise RuntimeError("Gemini response did not contain any text output.")

    def _gemini_describe_images(self, prompt: str, images: list[ImageAttachment]) -> list[str]:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Gemini multimodal support requires `google-genai`. Run `pip install -r requirements.txt`."
            ) from exc

        try:
            client = genai.Client(api_key=settings.google_api_key)
            descriptions: list[str] = []
            for image in images:
                image_bytes = _decode_data_url(image.data_url)
                response = client.models.generate_content(
                    model=settings.gemini_chat_model,
                    contents=[
                        prompt,
                        types.Part.from_bytes(data=image_bytes, mime_type=image.media_type),
                    ],
                )
                descriptions.append(_extract_response_text(response) or f"Image jointe recue: {image.name}.")
            return descriptions
        except Exception as exc:
            raise RuntimeError(f"Gemini image description failed: {exc}") from exc


def _decode_data_url(data_url: str) -> bytes:
    try:
        _, encoded = data_url.split(",", 1)
    except ValueError as exc:
        raise RuntimeError("Invalid image data URL.") from exc
    try:
        return base64.b64decode(encoded)
    except Exception as exc:
        raise RuntimeError("Invalid base64 image payload.") from exc


def _extract_response_text(response: Any) -> str:
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


def _read_analysis_list(analysis: Any | None, key: str) -> list[str]:
    if analysis is None:
        return []
    if isinstance(analysis, dict):
        value = analysis.get(key, [])
    else:
        value = getattr(analysis, key, [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]
