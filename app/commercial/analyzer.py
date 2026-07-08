from __future__ import annotations

import re
import unicodedata

from app.commercial.product_catalog import recommend_products
from app.config import settings
from schemas.commercial_schema import BuyingIntent, OpportunityStage, SavAdminAnalysis
from schemas.retrieval_schema import RetrievalResult


HIGH_INTENT_PATTERNS = (
    r"\b(devis|quotation|quote|prix|price|tarif|budget)\b",
    r"\b(commander|commande|acheter|buy|purchase)\b",
    r"\b(contact|rappel|callback|rdv|meeting|visit|visite)\b",
)
MEDIUM_INTENT_PATTERNS = (
    r"\b(besoin|need|recherche|looking for|cherche)\b",
    r"\b(solution|diffuseur|machine|product)\b",
    r"\b(installer|installation|deploy|setup)\b",
)
SURFACE_PATTERN = re.compile(
    r"\b\d{2,4}\s?(m2|m²|sqm|square meters?|metres? carres?|metres? carrés?)\b",
    re.IGNORECASE,
)
TIMELINE_PATTERN = re.compile(
    r"\b(today|this week|ce mois|urgent|asap|rapidement|soon|immediat|immediate)\b",
    re.IGNORECASE,
)
CONTACT_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b|\b\d{8,15}\b")
SECTOR_TERMS = (
    "hotel",
    "restaurant",
    "boutique",
    "bureau",
    "showroom",
    "clinique",
    "spa",
    "cafe",
    "magasin",
)


def analyze_commercial_opportunity(query: str, retrieval_result: RetrievalResult) -> SavAdminAnalysis:
    lowered = _normalize_text(query)
    lead_score = 0

    for pattern in HIGH_INTENT_PATTERNS:
        if re.search(pattern, lowered):
            lead_score += 30
    for pattern in MEDIUM_INTENT_PATTERNS:
        if re.search(pattern, lowered):
            lead_score += 15
    if SURFACE_PATTERN.search(query):
        lead_score += 10
    if TIMELINE_PATTERN.search(query):
        lead_score += 15
    if CONTACT_PATTERN.search(query):
        lead_score += 20

    matched_products = _extract_products(retrieval_result)
    if not matched_products:
        matched_products = recommend_products(query)
    if matched_products:
        lead_score += 10

    customer_needs = _extract_customer_needs(lowered, query)
    missing_information = _identify_missing_information(lowered, query)
    recommended_next_steps = _build_next_steps(matched_products, missing_information, lead_score)

    buying_intent = _classify_buying_intent(lead_score)
    opportunity_stage = _classify_opportunity_stage(lead_score, lowered)
    should_alert_admin = lead_score >= settings.admin_alert_min_score and opportunity_stage != OpportunityStage.none
    alert_reason = None
    if should_alert_admin:
        alert_reason = (
            f"Opportunite interne detectee avec un score de {lead_score} "
            f"au stade {opportunity_stage.value}."
        )

    return SavAdminAnalysis(
        buying_intent=buying_intent,
        opportunity_stage=opportunity_stage,
        lead_score=min(100, lead_score),
        matched_products=matched_products,
        customer_needs=customer_needs,
        missing_information=missing_information,
        recommended_next_steps=recommended_next_steps,
        should_alert_admin=should_alert_admin,
        alert_reason=alert_reason,
    )


def _extract_products(retrieval_result: RetrievalResult) -> list[str]:
    products: list[str] = []
    for hit in retrieval_result.hits[:5]:
        product = hit.metadata.get("produit") or hit.metadata.get("product")
        if isinstance(product, str) and product and product not in products:
            products.append(product)
    return products


def _extract_customer_needs(lowered: str, query: str) -> list[str]:
    needs: list[str] = []
    if SURFACE_PATTERN.search(query):
        needs.append("surface definie")
    if any(term in lowered for term in SECTOR_TERMS):
        needs.append("type de lieu identifie")
    if "premium" in lowered or "luxe" in lowered or "luxury" in lowered:
        needs.append("positionnement premium")
    if "maintenance" in lowered or "service" in lowered:
        needs.append("continuite de service")
    if "parfum" in lowered or "scent" in lowered or "olfactive" in lowered:
        needs.append("objectif d'identite olfactive")
    return needs


def _identify_missing_information(lowered: str, query: str) -> list[str]:
    missing: list[str] = []
    if not SURFACE_PATTERN.search(query):
        missing.append("surface a couvrir")
    if not any(term in lowered for term in SECTOR_TERMS):
        missing.append("type de lieu")
    if not TIMELINE_PATTERN.search(query):
        missing.append("delai du projet")
    if not any(term in lowered for term in ("budget", "prix", "price", "tarif")):
        missing.append("budget")
    if not CONTACT_PATTERN.search(query):
        missing.append("coordonnees de suivi")
    return missing


def _build_next_steps(matched_products: list[str], missing_information: list[str], lead_score: int) -> list[str]:
    next_steps: list[str] = []
    if matched_products:
        next_steps.append(f"Recommander {', '.join(matched_products[:2])} avec une justification courte.")
    if missing_information:
        next_steps.append("Poser des questions de qualification concises pour completer le dossier interne.")
    if lead_score >= settings.admin_alert_min_score:
        next_steps.append("Transmettre a l'administration pour verification et suivi.")
    else:
        next_steps.append("Faire avancer la demande avec une reponse operationnelle claire.")
    return next_steps


def _classify_buying_intent(lead_score: int) -> BuyingIntent:
    if lead_score >= 80:
        return BuyingIntent.ready_to_buy
    if lead_score >= 50:
        return BuyingIntent.active_evaluation
    if lead_score >= 20:
        return BuyingIntent.exploratory
    return BuyingIntent.unknown


def _classify_opportunity_stage(lead_score: int, lowered: str) -> OpportunityStage:
    if any(term in lowered for term in ("commande", "commander", "acheter", "buy", "purchase")):
        return OpportunityStage.potential_order
    if any(term in lowered for term in ("devis", "quotation", "quote")):
        return OpportunityStage.quotation_request
    if lead_score >= settings.admin_alert_min_score:
        return OpportunityStage.qualified_lead
    if lead_score >= 20:
        return OpportunityStage.nurturing
    return OpportunityStage.none


def _normalize_text(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.lower().split())
