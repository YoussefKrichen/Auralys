from __future__ import annotations

from app.agents.base import BaseAgent


class RecommendationAgent(BaseAgent):
    agent_name = "Recommendation Agent"
    state_key = "recommendation_analysis"

    def analyze(self, state):
        findings = list(state.get("findings", []))
        generated_recommendations = list(state.get("recommendations", []))
        if not generated_recommendations:
            generated_recommendations.append(
                "Aucune recommandation specifique disponible, demander une revue humaine."
            )

        next_actions = list(state.get("next_actions", []))
        if not next_actions:
            next_actions.append("Organiser une validation humaine du dossier.")

        summary = self.llm.summarize(
            agent_name=self.agent_name,
            prompt="Synthese des recommandations generee.",
            context={"findings": findings, "recommendations": generated_recommendations},
        )

        return {
            "summary": summary,
            "findings": findings[:3],
            "recommendations": generated_recommendations,
            "next_actions": next_actions,
            "priority": state.get("priority", "medium"),
            "requires_human_validation": state.get("requires_human_validation", False),
        }
