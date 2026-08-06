from __future__ import annotations

import json
import logging

from app.agent.core.intent_router import IntentRouter
from app.agent.core.response_builder import build_agent_response
from app.agent.core.session_manager import SessionManager
from app.agent.policies.action_policy import apply_policy, check_action_policy
from app.agent.skills.alert_management import AlertManagementSkill
from app.agent.skills.analytics import AnalyticsSkill
from app.agent.skills.ceo_reporting import CEOReportingSkill
from app.agent.skills.client_history import ClientHistorySkill
from app.agent.skills.general_question import GeneralQuestionSkill
from app.agent.skills.maintenance_diagnosis import MaintenanceDiagnosisSkill
from app.agent.skills.maintenance_fiche_intake import MaintenanceFicheIntakeSkill
from app.agent.skills.route_optimization import RouteOptimizationSkill
from app.agent.skills.sav_planning import SAVPlanningSkill
from app.agent.store import AgentStore
from app.agent.tools.memory import MemoryTool
from app.config import settings
from app.ingestion.fiche_writer import commit_agent_captured_fiche
from app.llm.citations import build_sources_prompt_block, extract_cited_sources, extract_citable_sources
from app.llm.reasoning import (
    build_agent_reasoning_signals,
    build_agent_reasoning_summary,
    build_internal_reasoning_protocol,
)
from app.llm.llm_service import LLMService
from schemas.agent_schema import AgentActionStatus, AgentChatRequest, AgentChatResponse, AgentIntent, ImageAttachment

logger = logging.getLogger(__name__)

_REPORT_FORMAT_HINTS = ("pdf", "excel", "xlsx", "xls")
_HISTORY_MESSAGE_LIMIT = 8
_HISTORY_MESSAGE_MAX_CHARS = 400


def _mentions_report_format(message: str) -> bool:
    lowered = message.lower()
    return any(hint in lowered for hint in _REPORT_FORMAT_HINTS)


class AgentOrchestrator:
    def __init__(
        self,
        *,
        intent_router: IntentRouter,
        session_manager: SessionManager,
        store: AgentStore,
        memory_tool: MemoryTool,
        llm_service: LLMService,
        client_history_skill: ClientHistorySkill,
        sav_planning_skill: SAVPlanningSkill,
        route_optimization_skill: RouteOptimizationSkill,
        alert_management_skill: AlertManagementSkill,
        maintenance_diagnosis_skill: MaintenanceDiagnosisSkill,
        ceo_reporting_skill: CEOReportingSkill,
        general_question_skill: GeneralQuestionSkill,
        maintenance_fiche_intake_skill: MaintenanceFicheIntakeSkill,
        analytics_skill: AnalyticsSkill,
    ) -> None:
        self.intent_router = intent_router
        self.session_manager = session_manager
        self.store = store
        self.memory_tool = memory_tool
        self.llm_service = llm_service
        self.skills = {
            AgentIntent.ASK_CLIENT_HISTORY: client_history_skill,
            AgentIntent.ASK_NEXT_SAV_DESTINATION: sav_planning_skill,
            AgentIntent.ASK_ROUTE_OPTIMIZATION: route_optimization_skill,
            AgentIntent.ASK_ALERTS: alert_management_skill,
            AgentIntent.ASK_MAINTENANCE_PROBLEM: maintenance_diagnosis_skill,
            AgentIntent.ASK_DAILY_REPORT: ceo_reporting_skill,
            AgentIntent.ASK_STOCK_STATUS: alert_management_skill,
            AgentIntent.GENERAL_QUESTION: general_question_skill,
            AgentIntent.SUBMIT_MAINTENANCE_FICHE: maintenance_fiche_intake_skill,
            AgentIntent.ASK_DATA_ANALYTICS: analytics_skill,
        }

    def handle_chat(self, request: AgentChatRequest) -> AgentChatResponse:
        # Resolved once, up front, and stamped onto the request so every
        # downstream step (intent routing, skill state like pending_report,
        # history lookup, persistence) agrees on the same key -- including
        # for the very first message of a brand new conversation, where the
        # client hasn't been given a key yet. Previously this key was only
        # generated *after* the skill ran, so a skill's own conversation_key
        # fallback (computed before persistence) could diverge from the key
        # actually persisted, orphaning any per-conversation state it saved.
        conversation_key = self._resolve_conversation_key(request)
        request = self._stamp_conversation_key(request, conversation_key)
        enriched_request = self._augment_request_with_images(request)
        intent = self._resolve_intent(enriched_request, conversation_key)
        skill = self.skills[intent]
        skill_result = skill.run(enriched_request)
        checked_actions = []
        for action in skill_result.proposed_actions:
            policy = check_action_policy(action.action_type, enriched_request.role)
            checked_actions.append(apply_policy(action, policy))
        if skill_result.skip_llm_polish:
            # The skill's answer embeds something that must survive verbatim
            # (a download link) -- still build reasoning signals, just skip
            # the LLM rewrite pass that could paraphrase the link away.
            synthesized = {
                "answer": skill_result.answer,
                "citations": [],
                "reasoning_signals": build_agent_reasoning_signals(
                    request=enriched_request,
                    intent=intent,
                    skill_result=skill_result,
                    checked_actions=checked_actions,
                    response_source="skill_deterministic",
                ),
            }
            synthesized["reasoning_summary"] = build_agent_reasoning_summary(synthesized["reasoning_signals"])
        else:
            synthesized = self._synthesize_agent_answer(
                request=enriched_request,
                intent=intent,
                skill_result=skill_result,
                checked_actions=checked_actions,
                conversation_key=conversation_key,
            )
        skill_result = skill_result.model_copy(update={"answer": synthesized["answer"]})
        conversation_id = None
        history_id = None
        try:
            conversation_id, conversation_key, history_id = self.session_manager.save_conversation(
                user_id=enriched_request.user_id,
                role=enriched_request.role,
                message=enriched_request.message,
                answer=skill_result.answer,
                intent=intent.value,
                conversation_key=conversation_key,
            )
        except Exception:
            # Agent persistence is optional at runtime; keep answering even if
            # storage is unavailable -- but keep the resolved conversation_key
            # (don't null it out) so the client still carries it into the next
            # turn instead of minting a fresh one and re-orphaning any skill
            # state (e.g. pending_report) already saved under this key.
            logger.exception("Failed to persist conversation for conversation_key=%r", conversation_key)
            conversation_id = None
            history_id = None
        persisted_actions = []
        if conversation_id is not None:
            for action in checked_actions:
                try:
                    action_id = self.store.save_action(conversation_id, action)
                    persisted_actions.append(action.model_copy(update={"id": action_id}))
                except Exception:
                    logger.exception(
                        "Failed to persist proposed action %r for conversation_id=%s",
                        action.action_type,
                        conversation_id,
                    )
                    persisted_actions.append(action)
        else:
            persisted_actions = checked_actions
        return build_agent_response(
            conversation_id=conversation_key,
            request_message=enriched_request.message,
            intent=intent,
            skill_result=skill_result,
            checked_actions=persisted_actions,
            reasoning_signals=synthesized["reasoning_signals"],
            reasoning_summary=synthesized["reasoning_summary"],
            citations=synthesized["citations"],
            history_id=history_id,
        )

    @staticmethod
    def _resolve_conversation_key(request: AgentChatRequest) -> str:
        existing = (
            request.conversation_id
            or str(request.context.get("conversation_id") or "").strip()
            or None
        )
        return existing or AgentStore.new_conversation_key(request.user_id, request.role)

    @staticmethod
    def _stamp_conversation_key(request: AgentChatRequest, conversation_key: str) -> AgentChatRequest:
        if request.conversation_id == conversation_key and request.context.get("conversation_id") == conversation_key:
            return request
        enriched_context = dict(request.context)
        enriched_context["conversation_id"] = conversation_key
        return request.model_copy(update={"conversation_id": conversation_key, "context": enriched_context})

    def _resolve_intent(self, request: AgentChatRequest, conversation_key: str) -> AgentIntent:
        """Route to ASK_DAILY_REPORT directly when this message looks like a
        reply to "PDF or Excel?" for a report the user already asked for.

        A bare "pdf"/"excel" reply has no report-related keywords in it, so
        the LLM/keyword intent router (see IntentRouter) has no reliable way
        to classify it -- it would most likely land on GENERAL_QUESTION,
        silently breaking the two-turn report flow. Checking for a pending
        report tied to this conversation sidesteps that instead of relying
        on the router to guess correctly.
        """
        if _mentions_report_format(request.message):
            try:
                if self.store.get_pending_report(conversation_key) is not None:
                    return AgentIntent.ASK_DAILY_REPORT
            except Exception:
                logger.exception(
                    "Failed to check pending report state for conversation_key=%r", conversation_key
                )
        return self.intent_router.detect_intent(request.message)

    def _augment_request_with_images(self, request: AgentChatRequest) -> AgentChatRequest:
        if not request.images:
            return request
        image_descriptions = self.llm_service.describe_images(
            (
                "Decris cette image pour un assistant interne SAV/CEO Aromair. "
                "Releve uniquement les elements visuels utiles a la decision: produit, machine, panne visible, document, "
                "texte lisible, etat materiel, quantites, contexte client. Reste concis."
            ),
            request.images,
        )
        attachment_lines = self._format_image_context(request.images, image_descriptions)
        enriched_message = request.message.strip()
        if attachment_lines:
            enriched_message = (
                f"{enriched_message}\n\nContexte image fourni:\n{attachment_lines}"
                if enriched_message
                else f"Analyse cette image.\n\nContexte image fourni:\n{attachment_lines}"
            )
        enriched_context = dict(request.context)
        enriched_context["image_descriptions"] = image_descriptions
        enriched_context["image_count"] = len(request.images)
        return request.model_copy(
            update={
                "message": enriched_message,
                "context": enriched_context,
            }
        )

    @staticmethod
    def _format_image_context(images: list[ImageAttachment], descriptions: list[str]) -> str:
        lines: list[str] = []
        for index, image in enumerate(images, start=1):
            description = descriptions[index - 1] if index - 1 < len(descriptions) else ""
            line = f"- image {index}: {image.name} ({image.media_type})"
            if description:
                line += f" -> {description}"
            lines.append(line)
        return "\n".join(lines)

    def _build_recent_history_block(self, conversation_key: str | None) -> str:
        """Prior turns of this conversation, oldest first, for the synthesis
        prompt -- the current turn isn't persisted yet at this point, so
        nothing here duplicates the "Message utilisateur" section below it.
        """
        if not conversation_key:
            return ""
        try:
            rows = self.store.fetch_recent_messages(conversation_key, limit=_HISTORY_MESSAGE_LIMIT)
        except Exception:
            logger.exception("Failed to fetch recent messages for conversation_key=%r", conversation_key)
            return ""
        lines = []
        for row in rows:
            speaker = "Auralys" if row.get("sender") == "assistant" else "Utilisateur"
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            if len(content) > _HISTORY_MESSAGE_MAX_CHARS:
                content = content[:_HISTORY_MESSAGE_MAX_CHARS] + "..."
            lines.append(f"- {speaker}: {content}")
        if not lines:
            return ""
        return "Historique recent de cette conversation (du plus ancien au plus recent) :\n" + "\n".join(lines) + "\n\n"

    def _synthesize_agent_answer(
        self,
        *,
        request: AgentChatRequest,
        intent: AgentIntent,
        skill_result,
        checked_actions,
        conversation_key: str | None = None,
    ) -> dict[str, str | dict]:
        history_block = self._build_recent_history_block(conversation_key)
        action_lines = "\n".join(
            f"- {action.action_type} | allowed={action.allowed} | approval={action.requires_approval} | reason={action.reason or 'none'}"
            for action in checked_actions
        ) or "- aucune action proposee"
        payload_excerpt = json.dumps(skill_result.payload or {}, ensure_ascii=False, default=str)
        if len(payload_excerpt) > 2500:
            payload_excerpt = payload_excerpt[:2500] + "..."
        citable_sources = extract_citable_sources(skill_result.payload or {})
        sources_block = build_sources_prompt_block(citable_sources)
        citation_rule = (
            "\n11. Cite le numero de source entre crochets juste apres une affirmation qui s'appuie dessus "
            "(ex: ... [2]), uniquement parmi les numeros listes ci-dessous. N'en invente aucun."
            if citable_sources
            else ""
        )
        business_rules = self.memory_tool.get_active_business_rules()
        business_rules_block = (
            "Corrections et regles validees par la direction (a respecter en priorite, "
            "elles remplacent toute information contraire) :\n"
            + "\n".join(f"- {rule}" for rule in business_rules)
            + "\n\n"
            if business_rules
            else ""
        )
        prompt = (
            f"Tu es {settings.agent_name}, l'assistante interne d'Aromair.\n"
            "Tu rediges la reponse finale d'un agent interne apres execution d'outils metier.\n"
            "La reponse doit etre en francais, concise, utile, naturelle, sans exposer la chaine de pensee complete.\n"
            "Tu peux t'appuyer sur le brouillon du skill, les sources, les actions proposees et le payload collecte.\n"
            "Ne mentionne un client, une intervention ou un historique precis que si le message utilisateur le demande "
            "explicitement. Pour une question generale ou une question sur ton identite/role, reponds sans exemple "
            "tire des sources, meme si des sources sont disponibles.\n"
            "Utilise l'historique recent ci-dessous uniquement pour comprendre une reference implicite du message "
            "actuel (ex: \"ça\", \"cette periode\", \"fais-le\"). Ne resume pas cet historique et n'y reponds pas a "
            "nouveau.\n"
            f"Ne fabrique pas de faits absents. Si l'information manque, dis-le clairement.{citation_rule}\n\n"
            f"{business_rules_block}"
            f"{build_internal_reasoning_protocol(mode='agent')}\n\n"
            f"{history_block}"
            f"Message utilisateur:\n{request.message}\n\n"
            f"Intent detectee:\n{intent.value}\n\n"
            f"Brouillon du skill:\n{skill_result.answer}\n\n"
            f"Sources:\n{', '.join(skill_result.sources) or 'aucune'}\n\n"
            f"Justification:\n{skill_result.justification or 'aucune'}\n\n"
            f"Actions proposees:\n{action_lines}\n\n"
            f"Payload utile:\n{payload_excerpt}\n\n"
            + (f"{sources_block}\n\n" if sources_block else "")
            + "Redige uniquement la meilleure reponse finale pour l'utilisateur."
        )
        details = self.llm_service.answer_details(
            prompt=prompt,
            fallback_context=skill_result.answer,
            query=request.message,
            analysis={"matched_products": [], "missing_information": []},
        )
        answer = str(details.get("answer") or "").strip()
        final_answer = answer or skill_result.answer
        citations = extract_cited_sources(final_answer, citable_sources)
        reasoning_signals = build_agent_reasoning_signals(
            request=request,
            intent=intent,
            skill_result=skill_result,
            checked_actions=checked_actions,
            response_source=str(details.get("response_source") or ""),
        )
        reasoning_summary = build_agent_reasoning_summary(reasoning_signals)
        return {
            "answer": final_answer,
            "citations": citations,
            "reasoning_signals": reasoning_signals,
            "reasoning_summary": reasoning_summary,
        }

    def save_feedback(
        self,
        *,
        conversation_key: str,
        user_id: int | None,
        rating: str,
        correction: str | None,
        should_remember: bool,
    ) -> dict[str, int]:
        conversation_id = self.store.resolve_conversation_id(conversation_key)
        if conversation_id is None:
            raise ValueError(f"Unknown conversation_key: {conversation_key!r}")
        feedback_id = self.memory_tool.save_feedback(
            conversation_id=conversation_id,
            user_id=user_id,
            rating=rating,
            correction=correction,
            should_remember=should_remember,
        )
        if should_remember and correction:
            self.memory_tool.save_memory(
                memory_type="FEEDBACK_MEMORY",
                content=correction,
                source=f"conversation:{conversation_id}",
                status="PENDING",
            )
        return {"feedback_id": feedback_id}

    def list_pending_actions(self) -> list[dict]:
        return self.store.list_pending_actions()

    def approve_action(self, action_id: int, approved_by: int | None, review_note: str | None = None) -> dict:
        action = self.store.get_action(action_id)
        if action is None:
            raise ValueError(f"Unknown action_id: {action_id!r}")
        payload = {"review_note": review_note} if review_note else {"status": "approved"}
        if action["action_type"] == "CREATE_MAINTENANCE_FICHE":
            fiche_payload = (action["input_json"] or {}).get("fiche")
            if not fiche_payload:
                raise ValueError(f"Action {action_id} has no staged fiche payload.")
            # Executed here rather than at proposal time: approval is the point at
            # which a human confirms the vision extraction is correct, so this is
            # the first moment it's safe to write into the source-of-truth tables.
            write_stats = commit_agent_captured_fiche(fiche_payload)
            payload = {**payload, **write_stats}
        return self.store.update_action_status(
            action_id=action_id,
            status=AgentActionStatus.APPROVED.value,
            approved_by=approved_by,
            output_json=payload,
        )

    def reject_action(self, action_id: int, approved_by: int | None, review_note: str | None = None) -> dict:
        payload = {"review_note": review_note} if review_note else {"status": "rejected"}
        return self.store.update_action_status(
            action_id=action_id,
            status=AgentActionStatus.REJECTED.value,
            approved_by=approved_by,
            output_json=payload,
        )

    def get_active_memory(self) -> list[dict]:
        return self.memory_tool.get_active_memory()
