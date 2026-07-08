from __future__ import annotations

import json
import mimetypes
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings


SUPPORTED_PASSTHROUGH_SUFFIXES = {".json", ".docx"}
SUPPORTED_MODEL_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class ExtractionResult:
    source_file: str
    status: str
    output_file: str | None = None
    detail: str | None = None


class EmailDownloadExtractionAgent:
    def __init__(self, *, destination_dir: str | Path | None = None) -> None:
        self.destination_dir = Path(destination_dir or settings.raw_data_dir) / "email_downloads"

    def extract_downloads(self, source_dir: str | Path) -> list[ExtractionResult]:
        source_root = Path(source_dir)
        results: list[ExtractionResult] = []
        for file_path in sorted(path for path in source_root.iterdir() if path.is_file()):
            results.append(self.extract_file(file_path))
        return results

    def extract_file(self, source_file: str | Path) -> ExtractionResult:
        path = Path(source_file)
        self.destination_dir.mkdir(parents=True, exist_ok=True)
        suffix = path.suffix.lower()

        if suffix in SUPPORTED_PASSTHROUGH_SUFFIXES:
            destination = self.destination_dir / path.name
            shutil.copy2(path, destination)
            return ExtractionResult(
                source_file=str(path),
                status="forwarded",
                output_file=str(destination),
            )

        if suffix not in SUPPORTED_MODEL_SUFFIXES:
            return ExtractionResult(
                source_file=str(path),
                status="skipped",
                detail=f"Unsupported attachment type `{suffix or 'unknown'}`.",
            )

        if not self._has_model_extractor():
            return ExtractionResult(
                source_file=str(path),
                status="pending_extraction",
                detail="GOOGLE_API_KEY is not configured for PDF/image extraction.",
            )

        try:
            payload = self._extract_structured_payload(path)
        except RuntimeError as exc:
            return ExtractionResult(
                source_file=str(path),
                status="failed",
                detail=str(exc),
            )
        destination = self.destination_dir / f"{path.stem}.extracted.json"
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return ExtractionResult(
            source_file=str(path),
            status="extracted",
            output_file=str(destination),
        )

    def _has_model_extractor(self) -> bool:
        return bool(settings.google_api_key)

    def _extract_structured_payload(self, source_file: Path) -> dict[str, Any]:
        prompt = self._build_prompt(source_file.name)
        response_text = self._run_gemini_extraction(source_file=source_file, prompt=prompt)
        payload = _parse_json_payload(response_text)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Extractor returned a non-object payload for {source_file.name}.")
        return payload

    def _run_gemini_extraction(self, *, source_file: Path, prompt: str) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Gemini extraction requires `google-genai`. Run `pip install -r requirements.txt`."
            ) from exc

        mime_type = mimetypes.guess_type(source_file.name)[0] or "application/octet-stream"
        attachment_bytes = source_file.read_bytes()

        try:
            client = genai.Client(api_key=settings.google_api_key)
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Part.from_bytes(data=attachment_bytes, mime_type=mime_type),
                    prompt,
                ],
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini extraction failed for {source_file.name}: {exc}") from exc

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
        raise RuntimeError(f"Gemini extraction did not return text for {source_file.name}.")

    @staticmethod
    def _build_prompt(filename: str) -> str:
        return f"""
You extract Aromair maintenance attachments into strict JSON for downstream ingestion.

File name: {filename}

Return JSON only. No markdown, no explanation.

Target shape:
{{
  "page_1": {{
    "document_type": "client_maintenance_form",
    "company_info": {{
      "version": null,
      "name": null,
      "slogan": null,
      "address": {{
        "residence": null,
        "street": null,
        "city_postal_code": null
      }}
    }},
    "maintenance_details": {{
      "client": null,
      "address": null,
      "date_raw": null,
      "time_raw": null,
      "technician_name": null,
      "client_maintenance_number": null,
      "sav_numbers": []
    }},
    "service_type": {{
      "demo": null,
      "livraison": null,
      "visite": null,
      "reparation": null,
      "echange": null
    }},
    "controle_diffuseur_recharge": [],
    "recharge_bouteille_effectuee": [],
    "probleme_recommandation": {{
      "probleme_rencontree_raw": null,
      "probleme_rencontree_code": null,
      "solution_proposee": null
    }},
    "enquete_satisfaction_client": {{
      "satisfied_service": null,
      "parfum_bien_diffuse": null
    }},
    "signature_cachet": {{
      "text": null
    }},
    "raw_payload": {{
      "source": "email_download_extraction"
    }}
  }}
}}

Rules:
- Preserve the original language from the document when copying text fields.
- Use null for missing scalar values.
- Use [] for missing lists.
- Extract all visible diffuser rows and recharge rows when present.
- Keep dates and times exactly as written in the document in `date_raw` and `time_raw`.
- If the attachment is not a maintenance form, still return the same shape and put the best summary into `probleme_recommandation.probleme_rencontree_raw`.
""".strip()


def _parse_json_payload(response_text: str) -> Any:
    stripped = response_text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Extractor returned invalid JSON: {exc}") from exc
