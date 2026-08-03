from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.db.postgres import PostgresDatabase
from app.ingestion.gold_csv_loader import load_gold_csv_to_postgres


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load data/gold/data_2025_2026_concat.csv into the `gold_visits` "
        "Postgres table (one row per visit, diffusers as JSONB). This does not "
        "change what OperationsDataTool reads live -- it makes the same data "
        "queryable via SQL for dashboards, ad hoc reporting, etc. Re-run after "
        "the CSV changes to keep the table in sync (rows for maintenance_numbers "
        "no longer in the CSV are removed).",
    )
    parser.add_argument(
        "--csv-path",
        default=settings.gold_data_csv_path,
        help="Path to the gold CSV. Default: from GOLD_DATA_CSV_PATH env var / settings.",
    )
    parser.add_argument(
        "--dsn",
        default=settings.postgres_dsn,
        help="Postgres DSN. Default: from POSTGRES_DSN env var.",
    )
    parser.add_argument("--json", action="store_true", help="Print output as JSON.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    database = PostgresDatabase(dsn=args.dsn)
    stats = load_gold_csv_to_postgres(csv_path=args.csv_path, database=database)

    if args.json:
        print(json.dumps(stats, indent=2))
        return
    print(f"VISITS_LOADED: {stats['visits_loaded']}")
    print(f"DISTINCT_CLIENTS: {stats['distinct_clients']}")
    print(f"ORPHANS_REMOVED: {stats['orphans_removed']}")


if __name__ == "__main__":
    main()
