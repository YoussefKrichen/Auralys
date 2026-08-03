from __future__ import annotations

from app.agent.tools.gold_data_source import load_gold_visits
from app.agent.tools.text_normalize import client_id as compute_client_id
from app.config import settings
from app.db import Database, default_database


def load_gold_csv_to_postgres(
    csv_path: str | None = None,
    database: Database | None = None,
) -> dict[str, int]:
    """Load the gold CSV into the `gold_visits` Postgres table -- a queryable
    mirror of the same grouped/cleaned data OperationsDataTool reads live from
    the CSV on every request. Independent of that live read path (not wired
    into it); run this whenever the CSV changes and something needs to query
    the data via SQL (e.g. scripts/load_gold_csv.py, dashboards, ad hoc reporting)."""
    database = database or default_database
    path = csv_path or settings.gold_data_csv_path
    visits = load_gold_visits(path)

    database.init_schema()
    keep_numbers = [visit.maintenance_number for visit in visits]
    with database.connection() as connection:
        for visit in visits:
            database.upsert_gold_visit(
                connection,
                {
                    "maintenance_number": visit.maintenance_number,
                    "client": visit.client,
                    "client_id": compute_client_id(visit.client) if visit.client else None,
                    "address": visit.address,
                    "service_date": visit.service_date,
                    "issue": visit.issue,
                    "diffusers": visit.diffusers,
                },
            )
        orphans_removed = database.delete_orphan_gold_visits(connection, keep_numbers)

    distinct_clients = len({compute_client_id(visit.client) for visit in visits if visit.client})
    return {
        "visits_loaded": len(visits),
        "distinct_clients": distinct_clients,
        "orphans_removed": orphans_removed,
    }


if __name__ == "__main__":
    print(load_gold_csv_to_postgres())
