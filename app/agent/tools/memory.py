from __future__ import annotations

from typing import Any

from app.agent.store import AgentStore


class MemoryTool:
    def __init__(self, store: AgentStore | None = None) -> None:
        self.store = store or AgentStore()

    def save_conversation(self, user_id: int, role: str, message: str, answer: str, intent: str) -> int:
        return self.store.save_conversation(
            user_id=user_id,
            role=role,
            message=message,
            answer=answer,
            intent=intent,
        )

    def save_feedback(
        self,
        conversation_id: int,
        rating: str,
        correction: str | None,
        should_remember: bool,
        user_id: int | None = None,
    ) -> int:
        return self.store.save_feedback(
            conversation_id=conversation_id,
            user_id=user_id,
            rating=rating,
            correction=correction,
            should_remember=should_remember,
        )

    def save_memory(
        self,
        memory_type: str,
        content: str,
        source: str,
        status: str = "PENDING",
    ) -> int:
        return self.store.save_memory(
            memory_type=memory_type,
            content=content,
            source=source,
            status=status,
        )

    def get_active_business_rules(self) -> list[str]:
        return self.store.get_active_business_rules()

    def get_user_preferences(self, user_id: int) -> dict[str, Any]:
        return self.store.get_user_preferences(user_id)

    def get_active_memory(self) -> list[dict[str, Any]]:
        return self.store.get_active_memory()

