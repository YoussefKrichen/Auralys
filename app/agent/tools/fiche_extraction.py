from __future__ import annotations

import uuid
from pathlib import Path

from app.ingestion.build_chunks import build_chunks_for_fiche
from app.ingestion.normalize import normalize_page
from app.llm.llm_service import LLMService
from schemas.agent_schema import ImageAttachment
from schemas.chunk_schema import ChunkSchema
from schemas.fiche_schema import FicheSchema


class FicheExtractionTool:
    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.llm_service = llm_service or LLMService()

    def extract(self, image: ImageAttachment) -> tuple[FicheSchema, list[ChunkSchema], float]:
        capture_id = uuid.uuid4().hex[:10]
        extracted_json = self.llm_service.extract_fiche_json(image)
        fiche = normalize_page(
            source_file=Path("agent_capture") / f"{capture_id}.json",
            page_key=f"capture_{capture_id}",
            payload=extracted_json,
        )
        chunks = build_chunks_for_fiche(fiche)
        confidence = _estimate_confidence(fiche)
        return fiche, chunks, confidence


def _estimate_confidence(fiche: FicheSchema) -> float:
    signals = [
        bool(fiche.client),
        bool(fiche.maintenance_details.date_raw),
        bool(fiche.controle_diffuseur_recharge),
        bool(
            fiche.probleme_recommandation.probleme_rencontree_raw
            or fiche.probleme_recommandation.solution_proposee
        ),
    ]
    return round(sum(1 for signal in signals if signal) / len(signals), 2)
