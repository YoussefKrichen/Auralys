from __future__ import annotations

from datetime import date, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
        parts = [
            self.model_diffuseur or self.model_diffuseur_raw,
            self.emplacement,
            self.nom_parfum,
            f"qty={self.qte_parfum_existante}" if self.qte_parfum_existante is not None else None,
            f"state={self.en_marche_arret}" if self.en_marche_arret else None,
            f"quality={self.qualite_diffusion}" if self.qualite_diffusion else None,
        ]
        return " | ".join(part for part in parts if part)


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
        parts = [
            f"{self.ml}ml" if self.ml is not None else None,
            self.parfum,
            self.reference_bouteille,
            self.emplacement,
            self.frequence_diffusion,
        ]
        return " | ".join(part for part in parts if part)


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

        service_labels = ", ".join(self.service_type.active_labels()) or "unknown service"
        diffusers = "; ".join(
            diffuser.compact_summary()
            for diffuser in self.controle_diffuseur_recharge
            if diffuser.compact_summary()
        )
        recharges = "; ".join(
            recharge.compact_summary()
            for recharge in self.recharge_bouteille_effectuee
            if recharge.compact_summary()
        )
        issue = self.probleme_recommandation.probleme_rencontree_raw
        solution = self.probleme_recommandation.solution_proposee
        lines = [
            f"Client: {self.client or 'unknown'}",
            f"Maintenance number: {self.maintenance_number or 'unknown'}",
            f"Address: {self.maintenance_details.address or 'unknown'}",
            f"Date: {self.maintenance_details.service_date or self.maintenance_details.date_raw or 'unknown'}",
            f"Time: {self.maintenance_details.service_time or self.maintenance_details.time_raw or 'unknown'}",
            f"Service type: {service_labels}",
            f"Diffusers: {diffusers or 'none'}",
            f"Recharges: {recharges or 'none'}",
            f"Issue: {issue or 'none'}",
            f"Recommendation: {solution or 'none'}",
            f"Signature: {self.signature_cachet.text or 'none'}",
        ]
        return "\n".join(lines)
