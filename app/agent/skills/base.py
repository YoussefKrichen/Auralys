from __future__ import annotations

from schemas.agent_schema import AgentChatRequest, SkillResult


class Skill:
    def run(self, request: AgentChatRequest) -> SkillResult:
        raise NotImplementedError

