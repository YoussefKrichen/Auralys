from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.build_chunks import build_chunks_for_fiche
from app.ingestion.client_reference_matcher import ClientReference, ClientReferenceMatch
from app.ingestion.csv_intervention_loader import (
    group_rows_by_fiche,
    load_fiches_from_csv,
    parse_intervention_csv,
)
from app.ingestion.normalize import load_fiches_from_file


FIXTURE_CSV = Path("data/test_fixtures/csv_interventions/interventions_sample.csv")


@pytest.fixture(autouse=True)
def _no_fuzzy_client_matching(monkeypatch):
    # Keep these tests independent from the live business reference CSV
    # (data/Fiche de Aromair - Sheet1.csv) so a change to that file can't flake them.
    monkeypatch.setattr(
        "app.ingestion.csv_intervention_loader.match_client_reference",
        lambda client, address: None,
    )


def test_parse_intervention_csv_realigns_comma_in_address():
    rows = parse_intervention_csv(FIXTURE_CSV)
    kantaoui_rows = [row for row in rows if row.n_fiche == "17783"]

    assert len(kantaoui_rows) == 1
    row = kantaoui_rows[0]
    assert row.address == "Kantaoui, Sousse"
    assert row.date_raw == "30/01/2026"
    assert row.technician_name == "Ghassen"
    assert row.model_diffuseur == "Aromair150"


def test_group_rows_by_fiche_groups_multi_row_visits():
    rows = parse_intervention_csv(FIXTURE_CSV)
    groups = group_rows_by_fiche(rows)

    n_fiche_keys = {key[0] for key in groups}
    assert n_fiche_keys == {"17780", "17783", "16020", "15949"}
    boumiza_key = next(key for key in groups if key[0] == "17780")
    assert len(groups[boumiza_key]) == 3


def test_group_rows_by_fiche_splits_reused_n_fiche_across_different_clients():
    # N_Fiche "15949" is reused in the raw export for two unrelated visits
    # (different client/address/date) - they must not be merged into one fiche.
    rows = parse_intervention_csv(FIXTURE_CSV)
    groups = group_rows_by_fiche(rows)

    matching_groups = [key for key in groups if key[0] == "15949"]
    assert len(matching_groups) == 2


def test_load_fiches_from_csv_builds_one_fiche_per_visit():
    fiches = load_fiches_from_csv(FIXTURE_CSV)

    # 5 visits: 17780, 17783, 16020, and two distinct visits both numbered 15949.
    assert len(fiches) == 5

    by_number = {}
    for fiche in fiches:
        by_number.setdefault(fiche.maintenance_number, []).append(fiche)

    boumiza = by_number["17780"][0]
    assert boumiza.client == "Boumiza Square"
    assert boumiza.document_type == "client_maintenance_form"
    assert len(boumiza.controle_diffuseur_recharge) == 3
    assert boumiza.probleme_recommandation.probleme_rencontree_raw == (
        "Changement de fréq = Diff +1 et Diff entre = 2-8"
    )

    kantaoui = by_number["17783"][0]
    assert kantaoui.maintenance_details.address == "Kantaoui, Sousse"
    assert kantaoui.maintenance_details.service_date.isoformat() == "2026-01-30"


def test_load_fiches_from_csv_keeps_reused_n_fiche_visits_separate():
    fiches = load_fiches_from_csv(FIXTURE_CSV)
    reused = [fiche for fiche in fiches if fiche.maintenance_number == "15949"]

    assert len(reused) == 2
    assert len({fiche.fiche_id for fiche in reused}) == 2  # unique fiche_ids

    clients = {fiche.client for fiche in reused}
    assert clients == {"Restaurant Red Castle", "Hotel Kantaoui"}

    red_castle = next(fiche for fiche in reused if fiche.client == "Restaurant Red Castle")
    hotel_kantaoui = next(fiche for fiche in reused if fiche.client == "Hotel Kantaoui")
    assert red_castle.maintenance_details.address == "P. Marina"
    assert hotel_kantaoui.maintenance_details.address == "Kantaoui, Sousse"
    assert "Changement Emplacement" not in (
        red_castle.probleme_recommandation.probleme_rencontree_raw or ""
    )


def test_load_fiches_from_csv_applies_fuzzy_client_reference_match(monkeypatch):
    monkeypatch.setattr(
        "app.ingestion.csv_intervention_loader.match_client_reference",
        lambda client, address: ClientReferenceMatch(
            reference=ClientReference(client_name="Boumiza Square (Sousse)", address="Sousse"),
            score=0.9,
            client_score=0.9,
            address_score=0.9,
        ),
    )

    fiches = load_fiches_from_csv(FIXTURE_CSV)
    boumiza = next(fiche for fiche in fiches if fiche.maintenance_number == "17780")

    assert boumiza.client == "Boumiza Square (Sousse)"


def test_load_fiches_from_csv_repairs_note_misplaced_in_nom_parfum():
    fiches = load_fiches_from_csv(FIXTURE_CSV)
    fiche = next(fiche for fiche in fiches if fiche.maintenance_number == "16020")

    assert fiche.controle_diffuseur_recharge == []
    assert "Livraison 5 bouteille 300 ml en stock client" in (
        fiche.probleme_recommandation.probleme_rencontree_raw or ""
    )


def test_load_fiches_from_file_dispatches_csv_by_suffix():
    fiches = load_fiches_from_file(FIXTURE_CSV)
    assert len(fiches) == 5
    assert {fiche.maintenance_number for fiche in fiches} == {
        "17780",
        "17783",
        "16020",
        "15949",
    }


def test_build_chunks_for_csv_fiche_does_not_error():
    fiches = load_fiches_from_csv(FIXTURE_CSV)
    boumiza = next(fiche for fiche in fiches if fiche.maintenance_number == "17780")

    chunks = build_chunks_for_fiche(boumiza)

    assert chunks
    assert any(chunk.metadata["client"] == "Boumiza Square" for chunk in chunks)
