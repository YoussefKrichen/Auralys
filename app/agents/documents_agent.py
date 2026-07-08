from __future__ import annotations

from app.agents.base import BaseAgent


class DocumentsAgent(BaseAgent):
    agent_name = "Documents Agent"
    state_key = "document_analysis"

    def analyze(self, state):
        documents = state.get("vector_context", [])
        findings = []
        recommendations = []
        next_actions = []

        if documents:
            top_document = documents[0]
            title = top_document.get("metadata", {}).get("title", top_document.get("document_id"))
            findings.append(
                f"Document principal retenu: {title} depuis {top_document.get('collection', 'qdrant')}."
            )
            findings.append(f"{len(documents)} document(s) ont alimente l'analyse.")
            recommendations.append("Relire le document principal avant validation humaine finale.")
            next_actions.append("Indexer tout nouveau rapport terrain dans Qdrant apres intervention.")
        else:
            findings.append("Aucun document semantique pertinent n'a ete retrouve.")
            recommendations.append("Completer la base documentaire avant de produire un diagnostic final.")
            next_actions.append("Indexer une fiche maintenance ou un email relie a la demande.")

        return {
            "summary": self.llm.summarize(
                agent_name=self.agent_name,
                prompt="Analyse documentaire terminee.",
                context={"documents": documents},
            ),
            "findings": findings,
            "recommendations": recommendations,
            "next_actions": next_actions,
            "priority": "medium",
            "requires_human_validation": not bool(documents),
        }
