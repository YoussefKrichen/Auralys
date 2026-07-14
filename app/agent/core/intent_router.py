from __future__ import annotations

import re
import unicodedata

from app.llm.llm_service import LLMService
from schemas.agent_schema import AgentIntent


class IntentRouter:
    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.llm_service = llm_service or LLMService()

    def detect_intent(self, message: str) -> AgentIntent:
        llm_intent = self._detect_intent_with_llm(message)
        if llm_intent is not None:
            return llm_intent
        return self._detect_intent_with_keywords(message)

    def _detect_intent_with_llm(self, message: str) -> AgentIntent | None:
        prompt = (
            "Tu es un routeur d'intention pour un assistant interne SAV/administration.\n"
            "Choisis exactement une intention dans cette liste et retourne uniquement son nom, sans phrase additionnelle:\n"
            "- ASK_CLIENT_HISTORY : historique client, interventions precedentes, reclamations, contexte client\n"
            "- ASK_NEXT_SAV_DESTINATION : prochaine destination SAV a privilegier maintenant, une seule destination\n"
            "- ASK_ROUTE_OPTIMIZATION : optimiser l'ordre de tout un planning/tournee de plusieurs visites, eviter les "
            "embouteillages/trafic, reduire la consommation de carburant, meilleur itineraire\n"
            "- ASK_ALERTS : alertes, urgences, retards, incidents prioritaires, stock faible critique\n"
            "- ASK_MAINTENANCE_PROBLEM : panne, probleme diffuseur, diagnostic, maintenance, verification technique\n"
            "- ASK_DAILY_REPORT : rapport, bilan, synthese de journee, reporting SAV ou direction\n"
            "- ASK_STOCK_STATUS : stock, bouteille, niveau, rupture, disponibilite materiel\n"
            "- SUBMIT_MAINTENANCE_FICHE : l'utilisateur envoie une photo d'une fiche de maintenance papier "
            "a numeriser et enregistrer dans la base\n"
            "- GENERAL_QUESTION : toute autre demande\n\n"
            f"Message utilisateur:\n{message}\n\n"
            "Retourne uniquement une valeur exacte de la liste."
        )
        try:
            raw = self.llm_service.generate_text(prompt).strip()
        except Exception:
            return None
        normalized = raw.strip().splitlines()[0].strip().strip("`").strip()
        try:
            return AgentIntent(normalized)
        except ValueError:
            return None

    def _detect_intent_with_keywords(self, message: str) -> AgentIntent:
        normalized = _normalize(message)

        if self._matches(
            normalized,
            (
                "nouvelle fiche",
                "ajouter cette fiche",
                "ajoute cette fiche",
                "enregistrer cette intervention",
                "enregistrer cette fiche",
                "scanner cette fiche",
                "numeriser cette fiche",
            ),
        ):
            return AgentIntent.SUBMIT_MAINTENANCE_FICHE
        if self._matches(normalized, ("historique", "client", "reclamation", "intervention precedente")):
            return AgentIntent.ASK_CLIENT_HISTORY
        if self._matches(
            normalized,
            (
                "optimiser",
                "optimise",
                "embouteillage",
                "trafic",
                "carburant",
                "consommation",
                "meilleur itineraire",
                "meilleur trajet",
                "ordre des visites",
                "tournee",
            ),
        ):
            return AgentIntent.ASK_ROUTE_OPTIMIZATION
        if self._matches(normalized, ("ou doit aller", "prochaine destination", "planning sav", "equipe sav")):
            return AgentIntent.ASK_NEXT_SAV_DESTINATION
        if self._matches(normalized, ("alertes", "alerte", "urgent", "retard", "stock faible")):
            return AgentIntent.ASK_ALERTS
        if self._matches(normalized, ("probleme", "diffuseur", "diagnostic", "panne", "maintenance")):
            return AgentIntent.ASK_MAINTENANCE_PROBLEM
        if self._matches(normalized, ("rapport", "bilan", "journee sav", "daily report")):
            return AgentIntent.ASK_DAILY_REPORT
        if self._matches(normalized, ("stock", "bouteille", "niveau", "rupture")):
            return AgentIntent.ASK_STOCK_STATUS
        return AgentIntent.GENERAL_QUESTION

    @staticmethod
    def extract_client_name(message: str) -> str | None:
        patterns = [
            r"client\s*[:\-]\s*([^,;\n]+)",
            r"chez\s+([^,;\n]+)",
            r"pour\s+([^,;\n]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _matches(message: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in message for keyword in keywords)


def _normalize(value: str) -> str:
    lowered = value.strip().lower()
    ascii_text = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.split())
