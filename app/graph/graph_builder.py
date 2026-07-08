from __future__ import annotations

from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph

from app.agents.client_agent import ClientAgent
from app.agents.coordinator import CoordinatorAgent
from app.agents.diffuseur_agent import DiffuseurAgent
from app.agents.documents_agent import DocumentsAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.report_learning_agent import ReportLearningAgent
from app.agents.sav_agent import SAVAgent
from app.agents.technicien_agent import TechnicienAgent
from app.graph.state import GraphState, InvokeRequest, InvokeResponse, initial_state
from app.services.response_builder import ResponseBuilder


@dataclass
class GraphNodes:
    coordinator: CoordinatorAgent
    sav_agent: SAVAgent
    client_agent: ClientAgent
    diffuseur_agent: DiffuseurAgent
    technicien_agent: TechnicienAgent
    documents_agent: DocumentsAgent
    recommendation_agent: RecommendationAgent
    report_learning_agent: ReportLearningAgent
    response_builder: ResponseBuilder


def build_graph(nodes: GraphNodes):
    workflow = StateGraph(GraphState)
    workflow.add_node("coordinator", nodes.coordinator)
    workflow.add_node("sav_agent", nodes.sav_agent)
    workflow.add_node("client_agent", nodes.client_agent)
    workflow.add_node("diffuseur_agent", nodes.diffuseur_agent)
    workflow.add_node("technicien_agent", nodes.technicien_agent)
    workflow.add_node("documents_agent", nodes.documents_agent)
    workflow.add_node("recommendation_agent", nodes.recommendation_agent)
    workflow.add_node("report_learning_agent", nodes.report_learning_agent)

    def response_node(state: GraphState):
        response = nodes.response_builder.build(state)
        return {
            "final_answer": response.model_dump(),
            "summary": response.summary,
            "findings": response.findings,
            "recommendations": response.recommendations,
            "priority": response.priority,
            "requires_human_validation": response.requires_human_validation,
            "next_actions": response.next_actions,
            "trace": response.trace,
        }

    workflow.add_node("response_builder", response_node)
    workflow.add_edge(START, "coordinator")
    workflow.add_edge("coordinator", "sav_agent")
    workflow.add_edge("sav_agent", "client_agent")
    workflow.add_edge("client_agent", "diffuseur_agent")
    workflow.add_edge("diffuseur_agent", "technicien_agent")
    workflow.add_edge("technicien_agent", "documents_agent")
    workflow.add_edge("documents_agent", "recommendation_agent")
    workflow.add_edge("recommendation_agent", "report_learning_agent")
    workflow.add_edge("report_learning_agent", "response_builder")
    workflow.add_edge("response_builder", END)
    return workflow.compile()


class AuralysGraphService:
    def __init__(self, nodes: GraphNodes) -> None:
        self.graph = build_graph(nodes)

    def invoke(self, request: InvokeRequest) -> InvokeResponse:
        result = self.graph.invoke(initial_state(request))
        return InvokeResponse.model_validate(result["final_answer"])
