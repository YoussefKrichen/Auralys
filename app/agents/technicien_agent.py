from __future__ import annotations

from app.agents.base import BaseAgent


class TechnicienAgent(BaseAgent):
    agent_name = "Technicien Agent"
    state_key = "technicien_analysis"

    def analyze(self, state):
        techniciens = state.get("sql_context", {}).get("techniciens", [])
        interventions = state.get("sql_context", {}).get("interventions", [])
        findings = []

        if techniciens:
            technicien = techniciens[0]
            findings.append(
                f"Technicien {technicien['name']} ({technicien['skill_level']}) disponible: {technicien['availability']}."
            )
        else:
            findings.append("Aucun technicien cible n'a ete retrouve.")

        if interventions:
            findings.append(f"{len(interventions)} intervention(s) liee(s) a la ressource technicien.")

        recommendations = [
            "Confirmer la charge du technicien avant de lui affecter une nouvelle intervention."
        ]
        next_actions = ["Verifier la couverture geographique par rapport au client concerne."]

        return {
            "summary": self.llm.summarize(
                agent_name=self.agent_name,
                prompt="Analyse technicien calculee.",
                context={"techniciens": techniciens, "interventions": interventions},
            ),
            "findings": findings,
            "recommendations": recommendations,
            "next_actions": next_actions,
            "priority": "medium",
            "requires_human_validation": False,
        }
