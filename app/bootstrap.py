from __future__ import annotations

from dataclasses import dataclass

from app.audio.speech_service import SpeechService
from app.agent.core.intent_router import IntentRouter
from app.agent.core.orchestrator import AgentOrchestrator
from app.agent.core.session_manager import SessionManager
from app.agent.skills.alert_management import AlertManagementSkill
from app.agent.skills.ceo_reporting import CEOReportingSkill
from app.agent.skills.client_history import ClientHistorySkill
from app.agent.skills.general_question import GeneralQuestionSkill
from app.agent.skills.maintenance_diagnosis import MaintenanceDiagnosisSkill
from app.agent.skills.maintenance_fiche_intake import MaintenanceFicheIntakeSkill
from app.agent.skills.route_optimization import RouteOptimizationSkill
from app.agent.skills.sav_planning import SAVPlanningSkill
from app.agent.store import AgentStore
from app.agent.tools.fiche_extraction import FicheExtractionTool
from app.agent.tools.maps import MapsTool
from app.agent.tools.memory import MemoryTool
from app.agent.tools.operations_data import OperationsDataTool
from app.agent.tools.rag import RAGTool
from app.agent.tools.routing import RouteOptimizationTool
from app.commercial.opportunity_logger import OpportunityLogger
from app.db import Database, default_database
from app.embeddings.embedding_service import EmbeddingService
from app.extraction.email_download_agent import EmailDownloadExtractionAgent
from app.history.history_service import HistoryService
from app.llm.answer_service import AnswerService
from app.llm.llm_service import LLMService
from app.pipeline.question_pipeline import QuestionPipeline
from app.review.review_service import ReviewService
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.qdrant_retriever import QdrantRetriever
from app.retrieval.sql_retriever import SQLRetriever


@dataclass
class AppContainer:
    database: Database = default_database

    def build_embedding_service(self) -> EmbeddingService:
        return EmbeddingService()

    def build_sql_retriever(self) -> SQLRetriever:
        return SQLRetriever(database=self.database)

    def build_qdrant_retriever(self) -> QdrantRetriever:
        return QdrantRetriever(embedding_service=self.build_embedding_service())

    def build_hybrid_retriever(self) -> HybridRetriever:
        return HybridRetriever(
            sql_retriever=self.build_sql_retriever(),
            qdrant_retriever=self.build_qdrant_retriever(),
        )

    def build_llm_service(self) -> LLMService:
        return LLMService()

    def build_speech_service(self) -> SpeechService:
        return SpeechService()

    def build_opportunity_logger(self) -> OpportunityLogger:
        return OpportunityLogger()

    def build_email_download_extraction_agent(self) -> EmailDownloadExtractionAgent:
        return EmailDownloadExtractionAgent()

    def build_history_service(self) -> HistoryService:
        return HistoryService(database=self.database)

    def build_review_service(self) -> ReviewService:
        return ReviewService(database=self.database)

    def build_agent_store(self) -> AgentStore:
        return AgentStore(database=self.database)

    def build_memory_tool(self) -> MemoryTool:
        return MemoryTool(store=self.build_agent_store())

    def build_operations_data_tool(self) -> OperationsDataTool:
        return OperationsDataTool(store=self.build_agent_store())

    def build_rag_tool(self) -> RAGTool:
        return RAGTool(
            retriever=self.build_hybrid_retriever(),
            store=self.build_agent_store(),
        )

    def build_maps_tool(self) -> MapsTool:
        return MapsTool(store=self.build_agent_store())

    def build_route_optimization_tool(self) -> RouteOptimizationTool:
        return RouteOptimizationTool(store=self.build_agent_store())

    def build_fiche_extraction_tool(self) -> FicheExtractionTool:
        return FicheExtractionTool(llm_service=self.build_llm_service())

    def build_agent_orchestrator(self) -> AgentOrchestrator:
        store = self.build_agent_store()
        memory_tool = self.build_memory_tool()
        operations_data_tool = self.build_operations_data_tool()
        rag_tool = self.build_rag_tool()
        maps_tool = self.build_maps_tool()
        route_optimization_tool = self.build_route_optimization_tool()
        fiche_extraction_tool = self.build_fiche_extraction_tool()
        return AgentOrchestrator(
            intent_router=IntentRouter(llm_service=self.build_llm_service()),
            session_manager=SessionManager(store),
            store=store,
            memory_tool=memory_tool,
            llm_service=self.build_llm_service(),
            client_history_skill=ClientHistorySkill(operations_data_tool=operations_data_tool, rag_tool=rag_tool),
            sav_planning_skill=SAVPlanningSkill(operations_data_tool=operations_data_tool, maps_tool=maps_tool),
            route_optimization_skill=RouteOptimizationSkill(
                operations_data_tool=operations_data_tool, routing_tool=route_optimization_tool
            ),
            alert_management_skill=AlertManagementSkill(operations_data_tool=operations_data_tool),
            maintenance_diagnosis_skill=MaintenanceDiagnosisSkill(operations_data_tool=operations_data_tool, rag_tool=rag_tool),
            ceo_reporting_skill=CEOReportingSkill(operations_data_tool=operations_data_tool),
            general_question_skill=GeneralQuestionSkill(rag_tool=rag_tool),
            maintenance_fiche_intake_skill=MaintenanceFicheIntakeSkill(fiche_extraction_tool=fiche_extraction_tool),
        )

    def build_answer_service(self) -> AnswerService:
        return AnswerService(
            retriever=self.build_hybrid_retriever(),
            llm_service=self.build_llm_service(),
            opportunity_logger=self.build_opportunity_logger(),
        )

    def build_question_pipeline(self) -> QuestionPipeline:
        return QuestionPipeline(
            answer_service=self.build_answer_service(),
            speech_service=self.build_speech_service(),
            history_service=self.build_history_service(),
        )
