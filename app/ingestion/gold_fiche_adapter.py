from __future__ import annotations

from app.agent.tools.gold_data_source import GoldVisit, load_gold_visits
from app.config import settings
from schemas.fiche_schema import DiffuserControl, FicheSchema, MaintenanceDetails, ProblemRecommendation


def load_gold_fiches(csv_path: str | None = None) -> list[FicheSchema]:
    """Adapt the gold CSV into FicheSchema objects so the existing chunk-building
    and retrieval pipeline (build_chunks.py, SQLRetriever, QdrantRetriever) can
    index visit history from gold data without any changes to that pipeline."""
    path = csv_path or settings.gold_data_csv_path
    visits = load_gold_visits(path)
    return [_visit_to_fiche(visit, source_file=str(path)) for visit in visits]


def _visit_to_fiche(visit: GoldVisit, *, source_file: str) -> FicheSchema:
    diffusers = [
        DiffuserControl(
            model_diffuseur=diffuser.get("model"),
            model_diffuseur_raw=diffuser.get("model"),
            emplacement=diffuser.get("emplacement"),
            qte_parfum_existante=diffuser.get("quantity_ml"),
        )
        for diffuser in visit.diffusers
    ]
    probleme_recommandation = (
        ProblemRecommendation(probleme_rencontree_raw=visit.issue)
        if visit.issue
        else ProblemRecommendation()
    )
    return FicheSchema(
        fiche_id=f"gold:{visit.maintenance_number}",
        source_file=source_file,
        page_key=f"visit:{visit.maintenance_number}",
        # Reused deliberately (not a new label) so hybrid_retriever._score_hit's
        # existing "client_maintenance_form" scoring prior applies unchanged.
        document_type="client_maintenance_form",
        maintenance_details=MaintenanceDetails(
            client=visit.client,
            address=visit.address,
            client_maintenance_number=visit.maintenance_number,
            service_date=visit.service_date,
        ),
        controle_diffuseur_recharge=diffusers,
        probleme_recommandation=probleme_recommandation,
    )
