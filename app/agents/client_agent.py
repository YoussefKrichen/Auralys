from __future__ import annotations

from app.agents.base import BaseAgent


class ClientAgent(BaseAgent):
    agent_name = "Client Agent"
    state_key = "client_analysis"

    def analyze(self, state):
        clients = state.get("sql_context", {}).get("clients", [])
        reclamations = state.get("sql_context", {}).get("reclamations", [])
        if clients:
            client = clients[0]
            findings = [
                f"Client cible: {client['name']} ({client['segment']}, {client['city']}).",
                f"Statut client: {client['status']}.",
            ]
        else:
            findings = ["Aucun client explicite n'a ete rattache a la demande."]

        if reclamations:
            findings.append(f"Historique: {len(reclamations)} reclamation(s) associee(s).")

        recommendations = [
            "Verifier la satisfaction client avant cloture si une intervention est ouverte."
        ]
        next_actions = ["Ajouter un retour client dans le prochain rapport SAV."]

        return {
            "summary": self.llm.summarize(
                agent_name=self.agent_name,
                prompt="Analyse client consolidee.",
                context={"clients": clients, "reclamations": reclamations},
            ),
            "findings": findings,
            "recommendations": recommendations,
            "next_actions": next_actions,
            "priority": "medium",
            "requires_human_validation": False,
        }
