from __future__ import annotations

from app.agents.base import BaseAgent


class SAVAgent(BaseAgent):
    agent_name = "SAV Agent"
    state_key = "sav_analysis"

    def analyze(self, state):
        interventions = state.get("sql_context", {}).get("interventions", [])
        reclamations = state.get("sql_context", {}).get("reclamations", [])
        open_interventions = [item for item in interventions if item.get("status") != "closed"]
        critical_claims = [item for item in reclamations if item.get("severity") == "critical"]

        findings = []
        if open_interventions:
            findings.append(f"{len(open_interventions)} intervention(s) SAV encore ouverte(s).")
        if critical_claims:
            findings.append(f"{len(critical_claims)} reclamation(s) critique(s) a traiter.")
        if not findings:
            findings.append("Aucun signal SAV bloquant detecte dans les donnees structurees.")

        recommendations = []
        next_actions = []
        priority = "medium"
        requires_human_validation = False

        if critical_claims:
            priority = "critical"
            requires_human_validation = True
            recommendations.append("Escalader immediatement le dossier au responsable SAV.")
            next_actions.append("Verifier la reclamation critique et confirmer le plan d'intervention.")
        elif open_interventions:
            priority = "high"
            recommendations.append("Confirmer le rendez-vous et valider la disponibilite du technicien.")
            next_actions.append("Mettre a jour le statut de l'intervention dans l'outil SAV.")
        else:
            recommendations.append("Maintenir une surveillance standard des equipements actifs.")
            next_actions.append("Archiver le dossier si aucun nouveau signal n'apparait.")

        return {
            "summary": self.llm.summarize(
                agent_name=self.agent_name,
                prompt="Analyse de l'etat SAV calculee.",
                context={"interventions": interventions, "reclamations": reclamations},
            ),
            "findings": findings,
            "recommendations": recommendations,
            "next_actions": next_actions,
            "priority": priority,
            "requires_human_validation": requires_human_validation,
        }
