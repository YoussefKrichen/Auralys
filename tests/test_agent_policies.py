from app.agent.policies.action_policy import apply_policy, check_action_policy
from schemas.agent_schema import AgentActionStatus, ProposedAction


def test_update_sav_planning_requires_approval():
    policy = check_action_policy("UPDATE_SAV_PLANNING", "CEO")
    checked = apply_policy(
        ProposedAction(action_type="UPDATE_SAV_PLANNING"),
        policy,
    )

    assert checked.allowed is True
    assert checked.requires_approval is True
    assert checked.status == AgentActionStatus.PENDING_APPROVAL


def test_delete_client_is_forbidden():
    policy = check_action_policy("DELETE_CLIENT", "CEO")
    checked = apply_policy(ProposedAction(action_type="DELETE_CLIENT"), policy)

    assert checked.allowed is False
    assert checked.status == AgentActionStatus.BLOCKED

