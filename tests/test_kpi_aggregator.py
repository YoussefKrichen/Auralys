from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from app.agent.tools.kpi_aggregator import (
    compute_kpis,
    format_period_label,
    parse_period_from_text,
    resolve_period_range,
)

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


def test_start_end_restricts_aggregation_to_the_given_range():
    kpis = compute_kpis(_write_csv(), start=date(2025, 2, 1), end=date(2025, 2, 28))

    assert kpis["totals"]["interventions"] == 2  # rows 101 and 102 only
    assert kpis["totals"]["clients"] == 2


def test_start_end_excludes_undated_rows():
    rows = _ROWS + ["105,Client E,Sousse,Client E Sousse,2025,,3,Visite,Astree,Entree,RG,10,5,,"]
    csv_path = Path(tempfile.mkdtemp()) / "gold.csv"
    csv_path.write_text(_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8-sig")

    kpis = compute_kpis(str(csv_path), start=date(2025, 1, 1), end=date(2025, 12, 31))

    assert kpis["totals"]["interventions"] == 6  # the undated row is dropped, not the whole file


def test_resolve_period_range_day():
    assert resolve_period_range("day", date(2026, 8, 4)) == (date(2026, 8, 4), date(2026, 8, 4))


def test_resolve_period_range_week_is_monday_to_sunday():
    # 2026-08-04 is a Tuesday.
    assert resolve_period_range("week", date(2026, 8, 4)) == (date(2026, 8, 3), date(2026, 8, 9))


def test_resolve_period_range_month_handles_leap_february():
    assert resolve_period_range("month", date(2024, 2, 10)) == (date(2024, 2, 1), date(2024, 2, 29))


def test_resolve_period_range_year():
    assert resolve_period_range("year", date(2026, 8, 4)) == (date(2026, 1, 1), date(2026, 12, 31))


def test_format_period_label_covers_all_periods():
    assert format_period_label("day", date(2026, 8, 4), date(2026, 8, 4)) == "4 aout 26"
    assert format_period_label("week", date(2026, 8, 3), date(2026, 8, 9)) == "Semaine du 3 aout 26 au 9 aout 26"
    assert format_period_label("month", date(2026, 8, 1), date(2026, 8, 31)) == "Aout 2026"
    assert format_period_label("year", date(2026, 1, 1), date(2026, 12, 31)) == "2026"


def test_parse_period_last_week_of_month_in_english():
    # "give me the report of the last week of june 2026" -- June 30 2026 is a
    # Tuesday, so the anchor should land on the ISO week that contains it.
    result = parse_period_from_text(
        "give me the report of the last week of june 2026", today=date(2026, 8, 4)
    )
    assert result == ("week", date(2026, 6, 30))
    assert resolve_period_range(*result) == (date(2026, 6, 29), date(2026, 7, 5))


def test_parse_period_last_week_of_month_in_french():
    result = parse_period_from_text(
        "rapport de la derniere semaine de juin 2026", today=date(2026, 8, 4)
    )
    assert result == ("week", date(2026, 6, 30))


def test_parse_period_month_and_year():
    result = parse_period_from_text("rapport du mois de mars 2026", today=date(2026, 8, 4))
    assert result == ("month", date(2026, 3, 1))


def test_parse_period_bare_year():
    result = parse_period_from_text("bilan de l'annee 2025", today=date(2026, 8, 4))
    assert result == ("year", date(2025, 1, 1))


def test_parse_period_explicit_date():
    result = parse_period_from_text("rapport du 15/03/2026", today=date(2026, 8, 4))
    assert result == ("day", date(2026, 3, 15))


def test_parse_period_keyword_only_defaults_to_today():
    result = parse_period_from_text("synthese de la semaine", today=date(2026, 8, 4))
    assert result == ("week", date(2026, 8, 4))


def test_parse_period_returns_none_when_no_period_referenced():
    assert parse_period_from_text("bonjour, qui es-tu ?", today=date(2026, 8, 4)) is None
