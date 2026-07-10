from __future__ import annotations

from datetime import date
from pathlib import Path

from app.ingestion.build_chunks import build_chunks_for_fiche
from app.ingestion.normalize import normalize_diffuser_catalog_entry
from schemas.chunk_schema import ChunkType
from schemas.fiche_schema import (
    BottleRecharge,
    DiffuserControl,
    FicheSchema,
    MaintenanceDetails,
    ProblemRecommendation,
    ServiceType,
)


def _maintenance_fiche(
    *,
    en_marche_arret: str | None = "M",
    fuite: str | None = "N",
    qualite_diffusion: str | None = "B",
    problem_code: str | None = "LIV",
) -> FicheSchema:
    return FicheSchema(
        fiche_id="test:page_1:014940",
        source_file="data/processed/Maintenance_json/test.json",
        page_key="page_1",
        document_type="client_maintenance_form",
        maintenance_details=MaintenanceDetails(
            client="BUSINESS Hotel",
            address="Tunis",
            client_maintenance_number="014940",
            service_date=date(2025, 2, 3),
        ),
        service_type=ServiceType(visite=True),
        controle_diffuseur_recharge=[
            DiffuserControl(
                model_diffuseur="Aromair100",
                emplacement="reception",
                qte_parfum_existante=0,
                en_marche_arret=en_marche_arret,
                fuite=fuite,
                qualite_diffusion=qualite_diffusion,
                frequence_diffusion_existante="5/10",
                plage_horaire_diffusion="7-12 / 17-20",
            )
        ],
        recharge_bouteille_effectuee=[
            BottleRecharge(
                ml=300,
                reference_bouteille="Simple (S)",
                emplacement="reception",
                frequence_diffusion="5/10",
            )
        ],
        probleme_recommandation=ProblemRecommendation(
            probleme_rencontree_raw="LIV 300ML",
            probleme_rencontree_code=problem_code,
        ),
    )


def test_maintenance_chunks_are_natural_language_and_non_redundant():
    fiche = _maintenance_fiche()
    chunks = build_chunks_for_fiche(fiche)

    assert [chunk.chunk_type for chunk in chunks] == [
        ChunkType.overview,
        ChunkType.diffuser,
        ChunkType.recharge,
        ChunkType.issue,
    ]

    overview, diffuser, recharge, issue = chunks

    # Overview only carries header info + counts, not the per-entity detail
    # that already lives in the diffuser/recharge/issue chunks below.
    assert "Diffuseurs suivis: 1" in overview.content
    assert "Aromair100" not in overview.content
    assert "|" not in overview.content

    # Diffuser chunk: full sentence, not pipe-delimited fragments, with
    # grounded code decoding (M -> "en marche", N -> "sans fuite") and the
    # raw code preserved for the field with no known legend (qualite_diffusion).
    assert "|" not in diffuser.content
    assert "en marche" in diffuser.content
    assert "sans fuite" in diffuser.content
    assert "qualite/couverture : B" in diffuser.content
    assert diffuser.metadata["emplacement"] == "reception"

    # Recharge chunk carries the bottle detail as a sentence.
    assert "300 ml" in recharge.content
    assert "Simple (S)" in recharge.content

    # Issue chunk decodes the problem code (LIV -> livraison) while keeping
    # the raw text verbatim, and never fabricates a translation it can't back up.
    assert "Motif : livraison" in issue.content
    assert "LIV 300ML" in issue.content


def test_unknown_single_letter_codes_fall_back_to_raw_code():
    fiche = _maintenance_fiche(en_marche_arret="X", fuite="Z")
    chunks = build_chunks_for_fiche(fiche)
    diffuser = next(chunk for chunk in chunks if chunk.chunk_type == ChunkType.diffuser)

    # No legend exists for these -> must not silently assert a guessed meaning.
    assert "etat (code X)" in diffuser.content
    assert "fuite (code Z)" in diffuser.content
    assert "en marche" not in diffuser.content
    assert "sans fuite" not in diffuser.content


def test_unknown_problem_code_does_not_fabricate_a_motif():
    fiche = _maintenance_fiche(problem_code="XYZ")
    chunks = build_chunks_for_fiche(fiche)
    issue = next(chunk for chunk in chunks if chunk.chunk_type == ChunkType.issue)

    assert "Motif :" not in issue.content
    assert "LIV 300ML" in issue.content


def test_catalog_entry_uses_product_framing_not_intervention_framing():
    fiche = normalize_diffuser_catalog_entry(
        source_file=Path("data/processed/diffuser_catalog_entry/aromair100.json"),
        page_key="1",
        payload={
            "produit": "Aromair100",
            "couverture": "jusqu'a 100 m2",
            "ideal_pour": ["boutiques", "bureaux"],
            "service_recommande": "recharge mensuelle",
            "argument_commercial": "Adapte aux petits espaces.",
        },
    )
    chunks = build_chunks_for_fiche(fiche)
    diffuser = next(chunk for chunk in chunks if chunk.chunk_type == ChunkType.diffuser)
    issue = next(chunk for chunk in chunks if chunk.chunk_type == ChunkType.issue)

    # Regression guard: catalog entries have no intervention/maintenance
    # number, so the maintenance-visit wrapper must not be applied to them.
    assert "intervention" not in diffuser.content
    assert "numero inconnu" not in diffuser.content
    assert "date inconnue" not in diffuser.content
    assert diffuser.content.startswith("Diffuseur 1 pour Aromair100")

    assert issue.content.startswith("Fiche produit Aromair100")
