from app.agent.core.intent_router import IntentRouter
from schemas.agent_schema import AgentIntent


def test_intent_router_detects_sav_destination_question():
    router = IntentRouter()

    intent = router.detect_intent("Où doit aller l'équipe SAV maintenant ?")

    assert intent == AgentIntent.ASK_NEXT_SAV_DESTINATION


def test_intent_router_detects_client_history_question():
    router = IntentRouter()

    intent = router.detect_intent("Montre-moi l'historique du client: Pharmacie Victoria")

    assert intent == AgentIntent.ASK_CLIENT_HISTORY


def test_intent_router_falls_back_to_general_question():
    router = IntentRouter()

    intent = router.detect_intent("Bonjour Auralys")

    assert intent == AgentIntent.GENERAL_QUESTION

