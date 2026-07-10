from __future__ import annotations

from datetime import date, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Codes decoded here are grounded either in the field name itself (plain French
# abbreviations, e.g. running/stopped) or in matching raw text observed in the
# dataset (e.g. "LIV" co-occurring with free-text mentioning "Livraison"/delivery).
# Other single-letter codes on the source forms (e.g. qualite_diffusion values
# like B/N/P/D/F/M/R) have no confirmed legend anywhere in this codebase, so they
# are intentionally left as raw codes rather than guessed at.
RUNNING_STATE_LABELS = {
    "M": "en marche",
    "A": "a l'arret",
}

LEAK_LABELS = {
    "N": "sans fuite",
    "O": "avec fuite",
    "Y": "avec fuite",
}

PROBLEM_CODE_LABELS = {
    "LIV": "livraison",
    "VIS": "visite",
}


class CompanyAddress(BaseModel):
    residence: str | None = None
    street: str | None = None
    city_postal_code: str | None = None


class CompanyInfo(BaseModel):
    version: str | None = None
    name: str | None = None
    slogan: str | None = None
    address: CompanyAddress = Field(default_factory=CompanyAddress)


class MaintenanceDetails(BaseModel):
    client: str | None = None
    address: str | None = None
    date_raw: str | None = None
    time_raw: str | None = None
    technician_name: str | None = None
    client_maintenance_number: str | None = None
    sav_numbers: list[str] = Field(default_factory=list)
    service_date: date | None = None
    service_time: time | None = None


class ServiceType(BaseModel):
    demo: bool | None = None
    livraison: bool | None = None
    visite: bool | None = None
    reparation: bool | None = None
    echange: bool | None = None

    def active_labels(self) -> list[str]:
        return [name for name, value in self.model_dump().items() if value]


class DiffuserControl(BaseModel):
    model_diffuseur_raw: str | None = None
    model_diffuseur: str | None = None
    emplacement: str | None = None
    reference_diffuseur_raw: str | None = None
    reference_diffuseur: str | None = None
    nom_parfum: str | None = None
    reference_bouteille_raw: str | None = None
    reference_bouteille: str | None = None
    qte_parfum_existante_raw: str | None = None
    qte_parfum_existante: int | None = None
    qualite_diffusion: str | None = None
    fuite: str | None = None
    en_marche_arret: str | None = None
    frequence_diffusion_existante: str | None = None
    plage_horaire_diffusion: str | None = None
    motif_arret: str | None = None

    @field_validator("qte_parfum_existante", mode="before")
    @classmethod
    def validate_quantity(cls, value):
        if value in (None, "", "-", "/"):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            digits = "".join(character for character in value if character.isdigit())
            return int(digits) if digits else None
        return None

    def compact_summary(self) -> str:
        model = self.model_diffuseur or self.model_diffuseur_raw
        details: list[str] = []
        if model:
            details.append(f"modele {model}")
        if self.emplacement:
            details.append(f"emplacement {self.emplacement}")
        if self.nom_parfum:
            details.append(f"parfum {self.nom_parfum}")
        if self.qte_parfum_existante is not None:
            details.append(f"quantite de parfum restante {self.qte_parfum_existante} ml")
        if self.en_marche_arret:
            state = RUNNING_STATE_LABELS.get(self.en_marche_arret.strip().upper())
            details.append(f"etat {state}" if state else f"etat (code {self.en_marche_arret})")
        if self.qualite_diffusion:
            details.append(f"indicateur qualite/couverture : {self.qualite_diffusion}")
        if self.fuite:
            leak = LEAK_LABELS.get(self.fuite.strip().upper())
            details.append(leak if leak else f"fuite (code {self.fuite})")
        if self.frequence_diffusion_existante:
            details.append(f"frequence {self.frequence_diffusion_existante}")
        if self.plage_horaire_diffusion:
            details.append(f"plage horaire {self.plage_horaire_diffusion}")
        if self.motif_arret:
            details.append(f"motif d'arret {self.motif_arret}")
        if not details:
            return ""
        return ", ".join(details)


class BottleRecharge(BaseModel):
    ml: int | None = None
    parfum: str | None = None
    reference_bouteille_raw: str | None = None
    reference_bouteille: str | None = None
    frequence_diffusion: str | None = None
    plage_horaire_fonctionnement: str | None = None
    emplacement: str | None = None

    @field_validator("ml", mode="before")
    @classmethod
    def validate_ml(cls, value):
        if value in (None, "", "-", "/"):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            digits = "".join(character for character in value if character.isdigit())
            return int(digits) if digits else None
        return None

    def compact_summary(self) -> str:
        details: list[str] = []
        if self.ml is not None:
            details.append(f"{self.ml} ml")
        if self.parfum:
            details.append(f"parfum {self.parfum}")
        if self.reference_bouteille:
            details.append(f"bouteille {self.reference_bouteille}")
        if self.emplacement:
            details.append(f"emplacement {self.emplacement}")
        if self.frequence_diffusion:
            details.append(f"frequence {self.frequence_diffusion}")
        if self.plage_horaire_fonctionnement:
            details.append(f"plage horaire {self.plage_horaire_fonctionnement}")
        if not details:
            return ""
        return ", ".join(details)


class ProblemRecommendation(BaseModel):
    probleme_rencontree_raw: str | None = None
    probleme_rencontree_code: str | None = None
    solution_proposee: str | None = None


class SatisfactionSurvey(BaseModel):
    satisfied_service: bool | None = None
    parfum_bien_diffuse: bool | None = None


class SignatureCachet(BaseModel):
    text: str | None = None


class FicheSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fiche_id: str
    source_file: str
    page_key: str
    source_image: str | None = None
    document_type: str = "client_maintenance_form"
    company_info: CompanyInfo = Field(default_factory=CompanyInfo)
    maintenance_details: MaintenanceDetails = Field(default_factory=MaintenanceDetails)
    service_type: ServiceType = Field(default_factory=ServiceType)
    controle_diffuseur_recharge: list[DiffuserControl] = Field(default_factory=list)
    recharge_bouteille_effectuee: list[BottleRecharge] = Field(default_factory=list)
    probleme_recommandation: ProblemRecommendation = Field(default_factory=ProblemRecommendation)
    enquete_satisfaction_client: SatisfactionSurvey = Field(default_factory=SatisfactionSurvey)
    signature_cachet: SignatureCachet = Field(default_factory=SignatureCachet)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def client(self) -> str | None:
        return self.maintenance_details.client

    @property
    def maintenance_number(self) -> str | None:
        return self.maintenance_details.client_maintenance_number

    def searchable_text(self) -> str:
        if self.document_type == "diffuser_catalog_entry":
            ideal_for = self.raw_payload.get("ideal_pour") or []
            advantages = self.raw_payload.get("avantages") or []
            lines = [
                f"Product: {self.raw_payload.get('produit') or self.client or 'unknown'}",
                f"Coverage: {self.raw_payload.get('couverture') or 'unknown'}",
                f"Ideal for: {', '.join(ideal_for) if ideal_for else 'unknown'}",
                f"Advantages: {', '.join(advantages) if advantages else 'unknown'}",
                f"Recommended service: {self.raw_payload.get('service_recommande') or 'unknown'}",
                f"Commercial argument: {self.raw_payload.get('argument_commercial') or 'unknown'}",
            ]
            return "\n".join(lines)

        if self.document_type == "knowledge_base_entry":
            question = self.raw_payload.get("question") or "unknown"
            answer = self.raw_payload.get("answer") or "unknown"
            category = self.raw_payload.get("category") or "general"
            lines = [
                f"Question: {question}",
                f"Answer: {answer}",
                f"Category: {category}",
                f"Source: {self.source_file}",
            ]
            return "\n".join(lines)

        # Deliberately excludes per-diffuser/per-recharge/issue detail: that content
        # already lives in its own dedicated chunk (see build_chunks.py). Repeating
        # it here would create near-duplicate chunks competing for the same rank.
        service_labels = ", ".join(self.service_type.active_labels()) or "service non precise"
        lines = [
            f"Client: {self.client or 'inconnu'}",
            f"Numero de maintenance: {self.maintenance_number or 'inconnu'}",
            f"Adresse: {self.maintenance_details.address or 'inconnue'}",
            f"Date: {self.maintenance_details.service_date or self.maintenance_details.date_raw or 'inconnue'}",
            f"Type de service: {service_labels}",
            f"Diffuseurs suivis: {len(self.controle_diffuseur_recharge)}",
            f"Recharges effectuees: {len(self.recharge_bouteille_effectuee)}",
        ]
        return "\n".join(lines)
