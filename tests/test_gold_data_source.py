from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from app.agent.tools.gold_data_source import load_gold_visits

_HEADER = (
    "maintenance_number,client,address,full_name,reference_year,service_date,month,"
    "source,model_diffuseur,emplacement,parfum,qte_restante,qte_livree,commentaire,technician_name"
)

_ROWS = [
    "100,Test Client,Site A,Test Client Site A,2026,2026-01-05,1,Controle,Aromair100,Salon,FE3,150,0,,",
    "100,Test Client,Site A,Test Client Site A,2026,2026-01-05,1,Controle,Aromair100,Cuisine,FE3,-,0,,",
    "200,Fuite Client,Site B,Fuite Client Site B,2026,2026-02-10,2,Controle,N/A,N/A,,0,0,Fuite tete bouteille,",
    "201,Neg Client,Site C,Neg Client Site C,2026,2026-02-11,2,Controle,Aromair100,Entree,FE2,50,0,"
    "Nous n'avons trouve aucun probleme,",
    "202,Quiet Client,Site D,Quiet Client Site D,2026,2026-02-12,2,Controle,Aromair100,Entree,FE2,50,0,,",
    "203,NoDate Client,Site E,NoDate Client Site E,2026,,2,Controle,Aromair100,Entree,FE2,50,0,,",
]


def _write_csv() -> str:
    # Uses tempfile directly rather than pytest's tmp_path fixture -- tmp_path's
    # cleanup scans %TEMP%\pytest-of-<user>, which is permission-locked in this
    # environment (OneDrive-synced temp dir), unrelated to the code under test.
    csv_path = Path(tempfile.mkdtemp()) / "gold.csv"
    csv_path.write_text(_HEADER + "\n" + "\n".join(_ROWS) + "\n", encoding="utf-8-sig")
    return str(csv_path)


def test_groups_multiple_diffuser_rows_into_one_visit_per_maintenance_number():
    visits = load_gold_visits(_write_csv())

    test_client_visit = next(v for v in visits if v.maintenance_number == "100")

    assert test_client_visit.client == "Test Client"
    assert test_client_visit.address == "Site A"
    assert test_client_visit.service_date == date(2026, 1, 5)
    assert len(test_client_visit.diffusers) == 2
    assert {d["emplacement"] for d in test_client_visit.diffusers} == {"Salon", "Cuisine"}


def test_cleans_junk_quantity_and_na_strings():
    visits = load_gold_visits(_write_csv())

    test_client_visit = next(v for v in visits if v.maintenance_number == "100")
    salon = next(d for d in test_client_visit.diffusers if d["emplacement"] == "Salon")
    cuisine = next(d for d in test_client_visit.diffusers if d["emplacement"] == "Cuisine")
    assert salon["quantity_ml"] == 150
    assert cuisine["quantity_ml"] is None  # "-" junk value coerced to None

    fuite_visit = next(v for v in visits if v.maintenance_number == "200")
    assert fuite_visit.diffusers[0]["model"] is None  # "N/A" coerced to None
    assert fuite_visit.diffusers[0]["emplacement"] is None


def test_missing_service_date_is_none():
    visits = load_gold_visits(_write_csv())

    nodate_visit = next(v for v in visits if v.maintenance_number == "203")

    assert nodate_visit.service_date is None


def test_issue_detected_from_positive_keyword_comment():
    visits = load_gold_visits(_write_csv())

    fuite_visit = next(v for v in visits if v.maintenance_number == "200")

    assert fuite_visit.issue == "Fuite tete bouteille"


def test_issue_not_flagged_when_comment_is_negated():
    visits = load_gold_visits(_write_csv())

    neg_visit = next(v for v in visits if v.maintenance_number == "201")

    assert neg_visit.issue is None


def test_issue_is_none_when_no_comment():
    visits = load_gold_visits(_write_csv())

    quiet_visit = next(v for v in visits if v.maintenance_number == "202")

    assert quiet_visit.issue is None
