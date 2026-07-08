from app.agent.skills.general_question import GeneralQuestionSkill
from schemas.agent_schema import AgentChatRequest


class _FakeRAGTool:
    def __init__(self):
        self.calls = 0

    def search_maintenance_files(self, query: str, limit: int = 3):
        self.calls += 1
        return {"hits": [{"content": f"Result for {query}"}]}


def test_general_question_greeting_skips_rag():
    rag_tool = _FakeRAGTool()
    skill = GeneralQuestionSkill(rag_tool)

    result = skill.run(
        AgentChatRequest(
            user_id=1,
            role="sav",
            message="Bonjour Auralys",
            context={},
        )
    )

    assert rag_tool.calls == 0
    assert result.payload["rag_used"] is False
    assert result.sources == []


def test_general_question_domain_query_can_use_rag():
    rag_tool = _FakeRAGTool()
    skill = GeneralQuestionSkill(rag_tool)

    result = skill.run(
        AgentChatRequest(
            user_id=1,
            role="sav",
            message="Donne-moi des informations sur ce diffuseur",
            context={},
        )
    )

    assert rag_tool.calls == 1
    assert result.payload["rag_used"] is True
    assert result.sources == ["RAG_MAINTENANCE"]
