from __future__ import annotations

import unicodedata

from app.agent.core.intent_router import IntentRouter
from app.agent.skills.base import Skill
from app.agent.tools.operations_data import OperationsDataTool
from schemas.agent_schema import AgentChatRequest, SkillResult

_RECENT_CLIENTS_KEYWORDS = (
    "liste des client",
    "liste de client",
    "derniers client",
    "dernier client",
    "client recemment",
    "clients recemment",
    "recemment servis",
    "client servis",
    "clients servis",
)


class AnalyticsSkill(Skill):
    def __init__(self, operations_data_tool: OperationsDataTool) -> None:
        self.operations_data_tool = operations_data_tool

    def run(self, request: AgentChatRequest) -> SkillResult:
        client = self._resolve_client(request)
        wants_recent_list = self._mentions_recent_clients(request.message)
        if client is not None and not wants_recent_list:
            return self._answer_diffuser_count(client)
        return self._answer_recent_clients()

    def _resolve_client(self, request: AgentChatRequest) -> dict | None:
        candidate = request.context.get("client_name") or IntentRouter.extract_client_name(request.message)
        if candidate:
            try:
                return self.operations_data_tool.get_client_by_name(candidate)
            except ValueError:
                pass
        return self.operations_data_tool.find_client_mentioned_in_text(request.message)

    def _answer_diffuser_count(self, client: dict) -> SkillResult:
        result = self.operations_data_tool.count_client_diffusers(client["client_id"])
        count = result["diffuser_count"]
        if count == 0:
            answer = f"Aucun diffuseur connu pour {client['client_name']} dans l'historique disponible."
            confidence = 0.3
        else:
            answer = (
                f"{client['client_name']} compte {count} diffuseur(s) identifie(s) "
                f"sur {result['raw_visit_count']} visite(s) archivee(s)."
            )
            confidence = 0.75
        return SkillResult(
            answer=answer,
            sources=["OPERATIONS_CLIENT_HISTORY"],
            confidence=confidence,
            justification="Comptage par emplacement canonique deduplique sur l'historique complet du client.",
            payload={"client": client, **result},
        )

    def _answer_recent_clients(self) -> SkillResult:
        result = self.operations_data_tool.list_recent_clients(limit=10)
        clients = result["clients"]
        if not clients:
            return SkillResult(
                answer="Aucun client avec une date de service exploitable n'a ete trouve.",
                sources=["OPERATIONS_CLIENT_ACTIVITY"],
                confidence=0.3,
                justification="Aucune fiche datee disponible.",
                payload=result,
            )
        names = ", ".join(f"{c['client_name']} ({c['last_service_date']})" for c in clients[:5])
        answer = f"Derniers clients servis : {names}."
        return SkillResult(
            answer=answer,
            sources=["OPERATIONS_CLIENT_ACTIVITY"],
            confidence=0.7,
            justification="Classement par date de derniere visite connue.",
            payload=result,
        )

    @staticmethod
    def _mentions_recent_clients(message: str) -> bool:
        normalized = _normalize(message)
        return any(keyword in normalized for keyword in _RECENT_CLIENTS_KEYWORDS)


def _normalize(value: str) -> str:
    lowered = value.strip().lower()
    ascii_text = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.split())
