from __future__ import annotations

from app.agents.base import BaseAgent


class ReportLearningAgent(BaseAgent):
    agent_name = "ReportLearning Agent"
    state_key = "report"

    def analyze(self, state):
        lessons = []
        if state.get("vector_context"):
            lessons.append("Les documents indexes confirment qu'un historique terrain enrichit le diagnostic.")
        if state.get("sql_context", {}).get("reclamations"):
            lessons.append("Les reclamations structurees doivent rester au centre des arbitrages SAV.")
        if not lessons:
            lessons.append("La demande manque de signaux pour produire un apprentissage durable.")

        return {
            "summary": self.llm.summarize(
                agent_name=self.agent_name,
                prompt="Rapport d'apprentissage prepare.",
                context={"lessons": lessons, "trace": state.get("trace", [])},
            ),
            "findings": lessons,
            "recommendations": ["Capitaliser les retours terrain dans la memoire semantique."],
            "next_actions": ["Ajouter le cas courant aux rapports d'apprentissage SAV."],
            "priority": state.get("priority", "medium"),
            "requires_human_validation": False,
        }
