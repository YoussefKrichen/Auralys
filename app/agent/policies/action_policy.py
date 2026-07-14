from __future__ import annotations

from schemas.agent_schema import ActionPolicyDecision, AgentActionStatus, ProposedAction


AUTO_ALLOWED_ACTIONS = {
    "SEARCH_CLIENT_HISTORY",
    "SUMMARIZE_MAINTENANCE",
    "GENERATE_REPORT_DRAFT",
    "RECOMMEND_ROUTE",
    "CREATE_LOW_RISK_ALERT",
}

APPROVAL_REQUIRED_ACTIONS = {
    "UPDATE_SAV_PLANNING",
    "ASSIGN_TECHNICIAN",
    "CREATE_OFFICIAL_INTERVENTION",
    "SEND_CLIENT_MESSAGE",
    "CHANGE_CLIENT_PRIORITY",
    "CREATE_MAINTENANCE_FICHE",
}

FORBIDDEN_ACTIONS = {
    "DELETE_CLIENT",
    "DELETE_INTERVENTION_HISTORY",
    "MODIFY_CONTRACT",
    "MAKE_FINANCIAL_DECISION",
    "SUSPEND_CLIENT",
}


def check_action_policy(action_type: str, user_role: str) -> ActionPolicyDecision:
    normalized_action = action_type.strip().upper()
    role = user_role.strip().upper()
    if normalized_action in FORBIDDEN_ACTIONS:
        return ActionPolicyDecision(
            allowed=False,
            requires_approval=False,
            reason="Action interdite par la politique beta.",
        )
    if normalized_action in APPROVAL_REQUIRED_ACTIONS:
        return ActionPolicyDecision(
            allowed=True,
            requires_approval=True,
            reason="Validation humaine requise pour cette action.",
        )
    if normalized_action in AUTO_ALLOWED_ACTIONS:
        return ActionPolicyDecision(
            allowed=True,
            requires_approval=False,
            reason=f"Action autorisee pour le role {role or 'UNKNOWN'}.",
        )
    return ActionPolicyDecision(
        allowed=True,
        requires_approval=True,
        reason="Action non cataloguee, validation humaine requise par prudence.",
    )


def apply_policy(action: ProposedAction, policy: ActionPolicyDecision) -> ProposedAction:
    if not policy.allowed:
        status = AgentActionStatus.BLOCKED
    elif policy.requires_approval:
        status = AgentActionStatus.PENDING_APPROVAL
    else:
        status = AgentActionStatus.ALLOWED
    return action.model_copy(
        update={
            "allowed": policy.allowed,
            "requires_approval": policy.requires_approval,
            "reason": policy.reason,
            "status": status,
        }
    )
