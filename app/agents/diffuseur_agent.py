from __future__ import annotations

from app.agents.base import BaseAgent


class DiffuseurAgent(BaseAgent):
    agent_name = "Diffuseur Agent"
    state_key = "diffuseur_analysis"

    def analyze(self, state):
        diffuseurs = state.get("sql_context", {}).get("diffuseurs", [])
        vector_context = state.get("vector_context", [])
        findings = []

        if diffuseurs:
            diffuseur = diffuseurs[0]
            findings.append(
                f"Diffuseur {diffuseur['model']} ({diffuseur['serial_number']}) en statut {diffuseur['status']}."
            )
        else:
            findings.append("Aucun diffuseur structure n'a ete retrouve.")

        if vector_context:
            findings.append(
                f"{len(vector_context)} document(s) semantique(s) relie(s) au diffuseur ont ete trouves."
            )

        recommendations = [
            "Comparer le statut terrain avec la derniere fiche maintenance avant toute recommandation finale."
        ]
        next_actions = ["Verifier l'historique du diffuseur dans les documents indexes."]
        priority = "high" if any("maintenance_due" in item for item in findings) else "medium"

        return {
            "summary": self.llm.summarize(
                agent_name=self.agent_name,
                prompt="Analyse diffuseur produite.",
                context={"diffuseurs": diffuseurs, "vector_context": vector_context},
            ),
            "findings": findings,
            "recommendations": recommendations,
            "next_actions": next_actions,
            "priority": priority,
            "requires_human_validation": False,
        }
