from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class BuyingIntent(str, Enum):
    unknown = "inconnu"
    exploratory = "exploratoire"
    active_evaluation = "evaluation_active"
    ready_to_buy = "pret_a_acheter"


class OpportunityStage(str, Enum):
    none = "aucun"
    nurturing = "a_developper"
    qualified_lead = "opportunite_qualifiee"
    quotation_request = "demande_de_devis"
    potential_order = "commande_potentielle"


class CommercialAnalysis(BaseModel):
    buying_intent: BuyingIntent = BuyingIntent.unknown
    opportunity_stage: OpportunityStage = OpportunityStage.none
    lead_score: int = 0
    matched_products: list[str] = Field(default_factory=list)
    customer_needs: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    should_alert_admin: bool = False
    alert_reason: str | None = None


SavAdminAnalysis = CommercialAnalysis


class AdminAlertEvent(BaseModel):
    query: str
    lead_score: int
    buying_intent: BuyingIntent
    opportunity_stage: OpportunityStage
    matched_products: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    alert_reason: str
