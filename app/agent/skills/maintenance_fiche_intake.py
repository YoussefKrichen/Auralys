from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from app.agent.skills.base import Skill
from app.agent.tools.fiche_extraction import FicheExtractionTool
from schemas.agent_schema import AgentChatRequest, ImageAttachment, ProposedAction, SkillResult

_UPLOADS_DIR = Path("data/agent_uploads")


class MaintenanceFicheIntakeSkill(Skill):
    def __init__(self, fiche_extraction_tool: FicheExtractionTool) -> None:
        self.fiche_extraction_tool = fiche_extraction_tool

    def run(self, request: AgentChatRequest) -> SkillResult:
        if not request.images:
            return SkillResult(
                answer=(
                    "Pour enregistrer une nouvelle fiche de maintenance, merci de joindre une photo "
                    "lisible de la fiche papier."
                ),
                sources=[],
                confidence=0.0,
                justification="Aucune photo jointe a la demande.",
            )

        image = request.images[0]
        try:
            fiche, chunks, confidence = self.fiche_extraction_tool.extract(image)
        except RuntimeError as exc:
            return SkillResult(
                answer=f"Je n'ai pas pu extraire les informations de cette fiche. Erreur technique : {exc}",
                sources=["VISION_EXTRACTION"],
                confidence=0.0,
                justification="L'extraction par vision a echoue.",
            )

        image_path = self._save_image(fiche.fiche_id, image)

        extra_images_note = ""
        if len(request.images) > 1:
            extra_images_note = (
                f" (les {len(request.images) - 1} autre(s) image(s) jointe(s) ont ete ignorees ; "
                "envoyez une fiche a la fois)"
            )

        client = fiche.client or "client non identifie"
        fiche_number = fiche.maintenance_number or "non identifie"
        date_display = fiche.maintenance_details.date_raw or "date non identifiee"
        problem = fiche.probleme_recommandation.probleme_rencontree_raw or "aucun probleme signale"
        answer = (
            f"J'ai lu la fiche de maintenance{extra_images_note} : numero de fiche {fiche_number}, "
            f"client {client}, date {date_display}, probleme signale : {problem}. Cette fiche est en attente "
            "de validation par un administrateur avant d'etre ajoutee definitivement a la base."
        )

        return SkillResult(
            answer=answer,
            proposed_actions=[
                ProposedAction(
                    action_type="CREATE_MAINTENANCE_FICHE",
                    input_json={
                        "fiche": fiche.model_dump(mode="json"),
                        "image_path": str(image_path),
                    },
                )
            ],
            sources=["VISION_EXTRACTION"],
            confidence=confidence,
            justification="Extraction par vision a partir de la photo de fiche jointe.",
            payload={"fiche": fiche.model_dump(mode="json"), "chunk_count": len(chunks)},
        )

    @staticmethod
    def _save_image(fiche_id: str, image: ImageAttachment) -> Path:
        _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        extension = mimetypes.guess_extension(image.media_type) or ".jpg"
        safe_name = fiche_id.replace(":", "_").replace("/", "_")
        image_path = _UPLOADS_DIR / f"{safe_name}{extension}"
        _, encoded = image.data_url.split(",", 1)
        image_path.write_bytes(base64.b64decode(encoded))
        return image_path
