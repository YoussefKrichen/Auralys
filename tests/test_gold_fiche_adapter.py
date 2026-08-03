from __future__ import annotations

from datetime import date

from app.ingestion.build_chunks import build_chunks
from app.ingestion.gold_fiche_adapter import _visit_to_fiche, load_gold_fiches
from app.agent.tools.gold_data_source import GoldVisit
from schemas.chunk_schema import ChunkType


def _visit(**overrides) -> GoldVisit:
    defaults = dict(
        maintenance_number="12345",
        client="Asteel Flash",
        address="Soukra",
        service_date=date(2026, 1, 6),
        diffusers=[
            {"model": "Aromair100", "emplacement": "B1 RDC", "quantity_ml": 50},
        ],
        issue=None,
    )
    defaults.update(overrides)
    return GoldVisit(**defaults)


def test_maps_identity_and_visit_fields():
    fiche = _visit_to_fiche(_visit(), source_file="data/gold/data_2025_2026_concat.csv")

    assert fiche.fiche_id == "gold:12345"
    assert fiche.page_key == "visit:12345"
    assert fiche.document_type == "client_maintenance_form"
    assert fiche.client == "Asteel Flash"
    assert fiche.maintenance_number == "12345"
    assert fiche.maintenance_details.address == "Soukra"
    assert fiche.maintenance_details.service_date == date(2026, 1, 6)


def test_maps_diffuser_fields_explicitly():
    fiche = _visit_to_fiche(_visit(), source_file="gold.csv")

    diffuser = fiche.controle_diffuseur_recharge[0]
    assert diffuser.model_diffuseur == "Aromair100"
    assert diffuser.emplacement == "B1 RDC"
    assert diffuser.qte_parfum_existante == 50


def test_maps_issue_into_probleme_recommandation():
    fiche = _visit_to_fiche(_visit(issue="Fuite tete bouteille"), source_file="gold.csv")

    assert fiche.probleme_recommandation.probleme_rencontree_raw == "Fuite tete bouteille"
    assert fiche.probleme_recommandation.solution_proposee is None


def test_no_issue_leaves_probleme_recommandation_empty():
    fiche = _visit_to_fiche(_visit(issue=None), source_file="gold.csv")

    assert fiche.probleme_recommandation.probleme_rencontree_raw is None


def test_build_chunks_produces_overview_and_diffuser_chunks_without_raising():
    fiche = _visit_to_fiche(_visit(issue="Fuite tete bouteille"), source_file="gold.csv")

    chunks = build_chunks([fiche])
    chunk_types = {chunk.chunk_type for chunk in chunks}

    assert ChunkType.overview in chunk_types
    assert ChunkType.diffuser in chunk_types
    assert ChunkType.issue in chunk_types
    # No gold equivalent for bottle recharges -- must never appear.
    assert ChunkType.recharge not in chunk_types


def test_build_chunks_handles_a_visit_with_no_diffusers_or_issue():
    fiche = _visit_to_fiche(_visit(diffusers=[], issue=None), source_file="gold.csv")

    chunks = build_chunks([fiche])

    assert chunks  # overview chunk still produced
    assert all(chunk.chunk_type == ChunkType.overview for chunk in chunks)


def test_load_gold_fiches_reads_real_csv_when_available():
    fiches = load_gold_fiches()

    assert len(fiches) > 0
    assert all(fiche.fiche_id.startswith("gold:") for fiche in fiches)
    assert all(fiche.document_type == "client_maintenance_form" for fiche in fiches)
