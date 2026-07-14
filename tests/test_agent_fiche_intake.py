from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import app.agent.skills.maintenance_fiche_intake as fiche_intake_module
from app.agent.policies.action_policy import check_action_policy
from app.agent.skills.maintenance_fiche_intake import MaintenanceFicheIntakeSkill
from app.agent.tools.fiche_extraction import FicheExtractionTool
from schemas.agent_schema import AgentChatRequest, ImageAttachment

_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _FakeLLMService:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def extract_fiche_json(self, image: ImageAttachment) -> dict:
        return self._payload


def _sample_extraction_payload() -> dict:
    return {
        "maintenance_details": {
            "client": "Pharmacie Test",
            "address": "Soukra",
            "date_raw": "10/02/25",
            "time_raw": "10H30",
            "technician_name": "Ali",
            "client_maintenance_number": "099999",
            "sav_numbers": ["99 000 000"],
        },
        "service_type": {"visite": True},
        "controle_diffuseur_recharge": [
            {
                "model_diffuseur": "Astree",
                "emplacement": "ENTREE",
                "nom_parfum": "Vanille",
                "fuite": "N",
            }
        ],
        "recharge_bouteille_effectuee": [],
        "probleme_recommandation": {
            "probleme_rencontree_raw": "Diffuseur ne fonctionne plus",
            "solution_proposee": "Remplacement de la pompe",
        },
        "enquete_satisfaction_client": {"satisfied_service": True},
    }


def _image_attachment() -> ImageAttachment:
    return ImageAttachment(
        name="fiche.png",
        media_type="image/png",
        data_url=f"data:image/png;base64,{_TINY_PNG_BASE64}",
    )


def test_fiche_extraction_tool_builds_fiche_and_chunks():
    tool = FicheExtractionTool(llm_service=_FakeLLMService(_sample_extraction_payload()))

    fiche, chunks, confidence = tool.extract(_image_attachment())

    assert fiche.client == "Pharmacie Test"
    assert fiche.maintenance_number == "099999"
    assert fiche.maintenance_details.service_date is not None
    assert chunks
    assert confidence == 1.0


def test_maintenance_fiche_intake_skill_proposes_pending_action(monkeypatch):
    upload_dir = Path(tempfile.mkdtemp(prefix="auralys-fiche-upload-"))
    monkeypatch.setattr(fiche_intake_module, "_UPLOADS_DIR", upload_dir)
    try:
        tool = FicheExtractionTool(llm_service=_FakeLLMService(_sample_extraction_payload()))
        skill = MaintenanceFicheIntakeSkill(fiche_extraction_tool=tool)
        request = AgentChatRequest(
            user_id=1,
            role="sav",
            message="Nouvelle fiche a enregistrer",
            images=[_image_attachment()],
        )

        result = skill.run(request)

        assert len(result.proposed_actions) == 1
        action = result.proposed_actions[0]
        assert action.action_type == "CREATE_MAINTENANCE_FICHE"
        assert action.input_json["fiche"]["maintenance_details"]["client"] == "Pharmacie Test"
        assert list(upload_dir.iterdir()), "the fiche photo should have been saved to disk"

        policy = check_action_policy(action.action_type, request.role)
        assert policy.allowed is True
        assert policy.requires_approval is True
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)


def test_maintenance_fiche_intake_skill_requires_image():
    tool = FicheExtractionTool(llm_service=_FakeLLMService(_sample_extraction_payload()))
    skill = MaintenanceFicheIntakeSkill(fiche_extraction_tool=tool)
    request = AgentChatRequest(user_id=1, role="sav", message="Nouvelle fiche a enregistrer", images=[])

    result = skill.run(request)

    assert not result.proposed_actions
    assert "photo" in result.answer.lower()
