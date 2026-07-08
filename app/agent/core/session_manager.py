from __future__ import annotations

from app.agent.store import AgentStore


class SessionManager:
    def __init__(self, store: AgentStore) -> None:
        self.store = store

    def save_conversation(
        self,
        *,
        user_id: int,
        role: str,
        message: str,
        answer: str,
        intent: str,
        conversation_key: str | None = None,
    ) -> tuple[int, str]:
        return self.store.save_conversation(
            user_id=user_id,
            role=role,
            message=message,
            answer=answer,
            intent=intent,
            conversation_key=conversation_key,
        )
