from __future__ import annotations

import re
import unicodedata

from app.agent.skills.base import Skill
from app.agent.tools.rag import RAGTool
from schemas.agent_schema import AgentChatRequest, SkillResult


class GeneralQuestionSkill(Skill):
    def __init__(self, rag_tool: RAGTool) -> None:
        self.rag_tool = rag_tool

    def run(self, request: AgentChatRequest) -> SkillResult:
        message = request.message.strip()
        if self._should_skip_rag(message):
            return SkillResult(
                answer=self._build_direct_answer(message),
                proposed_actions=[],
                sources=[],
                confidence=0.92,
                justification="Question conversationnelle ou meta; aucune recherche documentaire necessaire.",
                payload={"rag_used": False, "hits": []},
            )

        hits = self.rag_tool.search_maintenance_files(request.message, limit=3)["hits"]
        if hits:
            answer = f"J'ai retrouve des informations pertinentes: {hits[0]['content'][:220].strip()}"
            confidence = 0.62
        else:
            answer = "Je n'ai pas retrouve d'information suffisamment solide dans les sources disponibles."
            confidence = 0.25
        return SkillResult(
            answer=answer,
            proposed_actions=[],
            sources=["RAG_MAINTENANCE"],
            confidence=confidence,
            justification="Reponse generaliste basee sur la recherche documentaire locale.",
            payload={"rag_used": True, "hits": hits},
        )

    @classmethod
    def _should_skip_rag(cls, message: str) -> bool:
        normalized = _normalize(message)
        if not normalized:
            return True
        if cls._is_greeting(normalized):
            return True
        if cls._is_polite_short_turn(normalized):
            return True
        if cls._is_meta_assistant_question(normalized):
            return True
        return False

    @staticmethod
    def _is_greeting(message: str) -> bool:
        greeting_patterns = (
            r"^(bonjour|bonsoir|salut|hello|hey|coucou|yo)\b",
            r"^(bonjour|bonsoir|salut|hello|hey|coucou|yo)\b.*\b(auralys|assistant)\b",
        )
        return any(re.search(pattern, message) for pattern in greeting_patterns)

    @staticmethod
    def _is_polite_short_turn(message: str) -> bool:
        short_social_phrases = {
            "merci",
            "merci beaucoup",
            "ok merci",
            "super merci",
            "ca va",
            "ca roule",
            "d accord",
            "ok",
            "oui",
            "non",
        }
        if message in short_social_phrases:
            return True
        word_count = len(message.split())
        return word_count <= 4 and any(token in message for token in ("merci", "bonjour", "salut", "hello"))

    @staticmethod
    def _is_meta_assistant_question(message: str) -> bool:
        meta_patterns = (
            "qui es tu",
            "tu es qui",
            "que peux tu faire",
            "qu est ce que tu peux faire",
            "comment peux tu m aider",
            "aide moi",
            "help",
        )
        return any(pattern in message for pattern in meta_patterns)

    @staticmethod
    def _build_direct_answer(message: str) -> str:
        normalized = _normalize(message)
        if "merci" in normalized:
            return "Avec plaisir. Si vous avez une demande SAV, client ou stock, je peux vous aider."
        if any(token in normalized for token in ("qui es tu", "tu es qui")):
            return "Je suis Auralys, l'assistante interne d'Aromair pour le SAV, les clients, le stock et le suivi terrain."
        if any(token in normalized for token in ("que peux tu faire", "qu est ce que tu peux faire", "comment peux tu m aider", "aide moi", "help")):
            return "Je peux aider sur l'historique client, les problemes de maintenance, le planning SAV, les alertes, le stock et les questions operationnelles."
        return "Bonjour. Je peux vous aider sur le SAV, les clients, le stock et les operations Aromair."


def _normalize(value: str) -> str:
    lowered = value.strip().lower()
    ascii_text = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.split())
