from __future__ import annotations

from app.graph.state import Priority


class IntentRouter:
    def classify(self, *, query: str, requested_type: str | None = None) -> str:
        if requested_type:
            return requested_type

        normalized = query.casefold()
        if any(keyword in normalized for keyword in ("reclamation", "panne", "incident", "sav")):
            return "sav_analysis"
        if any(keyword in normalized for keyword in ("rapport", "retour d'experience", "learning")):
            return "report_learning"
        if any(keyword in normalized for keyword in ("document", "email", "fiche", "rapport technique")):
            return "document_analysis"
        if "technicien" in normalized:
            return "technicien_analysis"
        if "diffuseur" in normalized:
            return "diffuseur_analysis"
        if "client" in normalized:
            return "client_analysis"
        if any(keyword in normalized for keyword in ("recommand", "action", "priorite")):
            return "recommendation_analysis"
        return "sav_analysis"

    def select_agents(
        self,
        *,
        request_type: str,
        document_id: str | None = None,
    ) -> list[str]:
        mapping = {
            "sav_analysis": [
                "SAV Agent",
                "Client Agent",
                "Recommendation Agent",
                "ReportLearning Agent",
            ],
            "client_analysis": [
                "Client Agent",
                "Recommendation Agent",
            ],
            "diffuseur_analysis": [
                "Diffuseur Agent",
                "Documents Agent",
                "Recommendation Agent",
            ],
            "technicien_analysis": [
                "Technicien Agent",
                "Recommendation Agent",
            ],
            "document_analysis": [
                "Documents Agent",
                "Recommendation Agent",
                "ReportLearning Agent",
            ],
            "recommendation_analysis": [
                "SAV Agent",
                "Recommendation Agent",
                "ReportLearning Agent",
            ],
            "report_learning": [
                "Documents Agent",
                "ReportLearning Agent",
                "Recommendation Agent",
            ],
        }
        agents = list(mapping.get(request_type, ["SAV Agent", "Recommendation Agent"]))
        if document_id and "Documents Agent" not in agents:
            agents.insert(0, "Documents Agent")
        return agents

    def infer_priority(self, query: str) -> Priority:
        normalized = query.casefold()
        if any(keyword in normalized for keyword in ("critique", "bloque", "urgent", "panne totale")):
            return "critical"
        if any(keyword in normalized for keyword in ("risque", "incident", "reclamation")):
            return "high"
        if any(keyword in normalized for keyword in ("suivi", "verification")):
            return "medium"
        return "low"
