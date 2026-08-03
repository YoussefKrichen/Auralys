from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.db.postgres import PostgresDatabase

GROUP_BY_QUERIES = {
    "client": """
        SELECT client, COUNT(*) AS count
        FROM fiches
        {where}
        GROUP BY client
        ORDER BY count DESC, client ASC
        LIMIT %(limit)s
    """,
    "month": """
        SELECT to_char(date_trunc('month', service_date), 'YYYY-MM') AS bucket, COUNT(*) AS count
        FROM fiches
        {where}
        GROUP BY bucket
        ORDER BY bucket ASC
        LIMIT %(limit)s
    """,
    "service_type": """
        SELECT jsonb_array_elements_text(service_types) AS bucket, COUNT(*) AS count
        FROM fiches
        {where}
        GROUP BY bucket
        ORDER BY count DESC
        LIMIT %(limit)s
    """,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Filter and aggregate the live `fiches` table in Postgres "
        "(client interventions) -- e.g. counts per client, per month, per service type.",
    )
    parser.add_argument(
        "--dsn",
        default=settings.postgres_dsn,
        help="Postgres DSN. Default: from POSTGRES_DSN env var.",
    )
    parser.add_argument(
        "--client",
        help="Only include fiches whose client column contains this substring (case-insensitive).",
    )
    parser.add_argument(
        "--date-from",
        help="Only include fiches with service_date >= this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--date-to",
        help="Only include fiches with service_date <= this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--service-type",
        help="Only include fiches whose service_types array contains this value (e.g. visite, livraison, reparation).",
    )
    parser.add_argument(
        "--group-by",
        choices=sorted(GROUP_BY_QUERIES),
        default="client",
        help="Aggregation dimension. Default: client.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max number of groups to show. Default: 20.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print output as JSON.",
    )
    return parser


def build_where_clause(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    clauses: list[str] = []
    params: dict[str, object] = {}

    if args.client:
        clauses.append("client ILIKE %(client)s")
        params["client"] = f"%{args.client}%"
    if args.date_from:
        clauses.append("service_date >= %(date_from)s")
        params["date_from"] = args.date_from
    if args.date_to:
        clauses.append("service_date <= %(date_to)s")
        params["date_to"] = args.date_to
    if args.service_type:
        clauses.append("service_types @> %(service_type)s::jsonb")
        params["service_type"] = json.dumps([args.service_type])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    database = PostgresDatabase(dsn=args.dsn)
    where, params = build_where_clause(args)
    params["limit"] = max(args.limit, 1)

    total_sql = f"SELECT COUNT(*) FROM fiches {where}"
    group_sql = GROUP_BY_QUERIES[args.group_by].format(where=where)

    with database.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(total_sql, params)
            (total,) = cursor.fetchone()
        with connection.cursor() as cursor:
            cursor.execute(group_sql, params)
            rows = cursor.fetchall()

    result = {
        "dsn": args.dsn,
        "filters": {
            "client": args.client,
            "date_from": args.date_from,
            "date_to": args.date_to,
            "service_type": args.service_type,
        },
        "total_matching_fiches": total,
        "group_by": args.group_by,
        "groups": [{"bucket": bucket, "count": count} for bucket, count in rows],
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return

    print(f"TOTAL_MATCHING_FICHES: {result['total_matching_fiches']}")
    print(f"GROUP_BY: {result['group_by']}")
    for group in result["groups"]:
        print(f"{group['bucket']!s:<40} {group['count']}")


if __name__ == "__main__":
    main()
