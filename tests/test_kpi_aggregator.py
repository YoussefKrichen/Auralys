from __future__ import annotations

import tempfile
from pathlib import Path

from app.agent.tools.kpi_aggregator import compute_kpis

_HEADER = (
    "maintenance_number,client,address,full_name,reference_year,service_date,month,"
    "source,model_diffuseur,emplacement,parfum,qte_restante,qte_livree,commentaire,technician_name"
)

_ROWS = [
    "100,Client A,Lac1,Client A Lac1,2025,2025-01-05,1,Controle,Astree,Salon,RG,10,50,,",
    "100,Client A,Lac1,Client A Lac1,2025,2025-01-05,1,Controle,Astree,Cuisine,RG,10,50,,",
    "101,Client A,Lac 1,Client A Lac 1,2025,2025-02-10,2,Recharge,Astree,Entree,TH,10,20,,",
    "102,Client B,Lac2,Client B Lac2,2025,2025-02-11,2,Visite,N/A,N/A,,0,0,,",
    "103,Client C,Sousse,Client C Sousse,2025,2025-03-01,3,Livraison,Zee300,Entree,RG,10,30,,",
    "104,Client D,Sousse,Client D Sousse,2025,2025-03-15,3,Echange,Zee300,Entree,TH,10,10,,",
]


def _write_csv() -> str:
    # Uses tempfile directly rather than pytest's tmp_path fixture -- tmp_path's
    # cleanup scans %TEMP%\pytest-of-<user>, which is permission-locked in this
    # environment (OneDrive-synced temp dir), unrelated to the code under test.
    csv_path = Path(tempfile.mkdtemp()) / "gold.csv"
    csv_path.write_text(_HEADER + "\n" + "\n".join(_ROWS) + "\n", encoding="utf-8-sig")
    return str(csv_path)


def test_totals_count_rows_not_grouped_visits():
    kpis = compute_kpis(_write_csv())

    assert kpis["totals"]["interventions"] == 6
    assert kpis["totals"]["clients"] == 4
    assert kpis["totals"]["volume_livre"] == 160


def test_period_spans_first_to_last_service_date():
    kpis = compute_kpis(_write_csv())

    assert kpis["period"] == {"start": "5 janv. 25", "end": "15 mars 25"}


def test_place_variants_with_and_without_space_are_merged():
    kpis = compute_kpis(_write_csv())

    villes = {row["name"]: row["count"] for row in kpis["villes_top"]}
    assert villes["Lac 1"] == 3  # "Lac1" (2 rows) + "Lac 1" (1 row)
    assert villes["Lac 2"] == 1


def test_na_model_diffuseur_is_excluded_from_top_lists():
    kpis = compute_kpis(_write_csv())

    models = {row["model"] for row in kpis["diffuseurs_by_clients"]}
    assert "N/A" not in models


def test_source_breakdown_buckets_unrecognized_sources_as_autres():
    kpis = compute_kpis(_write_csv())

    breakdown = {row["label"]: row["pct"] for row in kpis["source_breakdown"]}
    assert breakdown["Autres"] == round(1 / 6 * 100, 1)  # only "Echange" falls outside the known buckets


def test_monthly_trend_fills_zero_count_months():
    kpis = compute_kpis(_write_csv())

    labels = [row["label"] for row in kpis["monthly_trend"]]
    assert labels == ["Jan 25", "Fev 25", "Mar 25"]
    fev = next(row for row in kpis["monthly_trend"] if row["label"] == "Fev 25")
    assert fev["count"] == 2  # rows 101 (2025-02-10) and 102 (2025-02-11)
    assert fev["has_data"] is True
