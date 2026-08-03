from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.ingestion.gold_csv_loader import load_gold_csv_to_postgres

_HEADER = (
    "maintenance_number,client,address,full_name,reference_year,service_date,month,"
    "source,model_diffuseur,emplacement,parfum,qte_restante,qte_livree,commentaire,technician_name"
)

_ROWS = [
    "100,Asteel Flash,Soukra,Asteel Flash Soukra,2026,2026-01-05,1,Controle,Aromair100,B1 RDC,FE3,150,0,,",
    "100,Asteel Flash,Soukra,Asteel Flash Soukra,2026,2026-01-05,1,Controle,Aromair100,B2 couloir,FE3,80,0,,",
    "101,Asteel flash,Soukra,Asteel flash Soukra,2026,2026-03-12,3,Controle,Aromair100,BL1RDC,FE3,40,0,"
    "Fuite tete bouteille,",
    "102,Finopti,Charguia,Finopti Charguia,2026,2026-02-01,2,Controle,Aromair150,Entree,FC,50,0,,",
]


def _write_csv() -> str:
    # tempfile directly, not pytest's tmp_path fixture -- see test_gold_data_source.py.
    csv_path = Path(tempfile.mkdtemp()) / "gold.csv"
    csv_path.write_text(_HEADER + "\n" + "\n".join(_ROWS) + "\n", encoding="utf-8-sig")
    return str(csv_path)


class _FakeDatabase:
    def __init__(self) -> None:
        self.schema_initialized = False
        self.upserted: list[dict] = []
        self.delete_orphan_calls: list[list[str]] = []

    def init_schema(self) -> None:
        self.schema_initialized = True

    @contextmanager
    def connection(self):
        yield object()

    def upsert_gold_visit(self, connection, visit_row: dict) -> None:
        self.upserted.append(visit_row)

    def delete_orphan_gold_visits(self, connection, keep_maintenance_numbers: list[str]) -> int:
        self.delete_orphan_calls.append(list(keep_maintenance_numbers))
        return 0


def test_loads_every_visit_and_initializes_schema():
    database = _FakeDatabase()

    stats = load_gold_csv_to_postgres(csv_path=_write_csv(), database=database)

    assert database.schema_initialized
    assert stats["visits_loaded"] == 3
    assert {row["maintenance_number"] for row in database.upserted} == {"100", "101", "102"}


def test_groups_diffusers_and_derives_client_id():
    database = _FakeDatabase()

    load_gold_csv_to_postgres(csv_path=_write_csv(), database=database)

    visit_100 = next(row for row in database.upserted if row["maintenance_number"] == "100")
    assert len(visit_100["diffusers"]) == 2
    assert visit_100["client_id"] == "asteel-flash"


def test_client_id_merges_casing_variants_for_distinct_client_count():
    database = _FakeDatabase()

    stats = load_gold_csv_to_postgres(csv_path=_write_csv(), database=database)

    # "Asteel Flash" (visit 100) and "Asteel flash" (visit 101) must count as one client.
    assert stats["distinct_clients"] == 2


def test_carries_issue_derived_from_commentaire():
    database = _FakeDatabase()

    load_gold_csv_to_postgres(csv_path=_write_csv(), database=database)

    visit_101 = next(row for row in database.upserted if row["maintenance_number"] == "101")
    assert visit_101["issue"] == "Fuite tete bouteille"


def test_passes_all_current_maintenance_numbers_to_orphan_cleanup():
    database = _FakeDatabase()

    load_gold_csv_to_postgres(csv_path=_write_csv(), database=database)

    assert len(database.delete_orphan_calls) == 1
    assert set(database.delete_orphan_calls[0]) == {"100", "101", "102"}
