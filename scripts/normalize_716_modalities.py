from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ingestion.export_unique_values import export_unique_values


JSON_DIRECTORIES = (
    Path("data/raw_json"),
    Path("data/processed/maintenance"),
    Path("data/processed/Maintenance_json"),
)

CSV_PATH = Path("data/processed_csv/client_maintenance_form.csv")

MENZAH_PATTERN = re.compile(r"^men(z|s)?ah?\s*6$", re.IGNORECASE)


@dataclass
class UpdateStats:
    json_files_changed: int = 0
    csv_rows_changed: int = 0
    client_updates: int = 0
    searchable_text_updates: int = 0


def _is_menzah6(value: str | None) -> bool:
    if not value:
        return False
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return bool(MENZAH_PATTERN.match(cleaned))


def normalize_client(client: str | None, address: str | None) -> str | None:
    if client is None:
        return None
    cleaned_client = str(client).strip()

    if cleaned_client == "716 HT":
        return "716 Menzah6"
    if cleaned_client == "716" and _is_menzah6(address):
        return "716 Menzah6"
    if _is_menzah6(cleaned_client):
        return "716 Menzah6"
    return cleaned_client


def walk_json(payload: Any, stats: UpdateStats) -> bool:
    changed = False

    if isinstance(payload, dict):
        maintenance_details = payload.get("maintenance_details")
        if isinstance(maintenance_details, dict):
            client = maintenance_details.get("client")
            address = maintenance_details.get("address")
            normalized_client = normalize_client(client, address)
            if normalized_client != client:
                maintenance_details["client"] = normalized_client
                stats.client_updates += 1
                changed = True

        raw_payload = payload.get("raw_payload")
        if isinstance(raw_payload, dict):
            raw_maintenance = raw_payload.get("maintenance_details")
            if isinstance(raw_maintenance, dict):
                client = raw_maintenance.get("client")
                address = raw_maintenance.get("address")
                normalized_client = normalize_client(client, address)
                if normalized_client != client:
                    raw_maintenance["client"] = normalized_client
                    stats.client_updates += 1
                    changed = True

        for value in payload.values():
            if isinstance(value, (dict, list)) and walk_json(value, stats):
                changed = True
        return changed

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, (dict, list)) and walk_json(item, stats):
                changed = True
        return changed

    return False


def process_json_files(stats: UpdateStats) -> None:
    for directory in JSON_DIRECTORIES:
        for path in directory.rglob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if walk_json(payload, stats):
                path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                stats.json_files_changed += 1


def normalize_searchable_text(value: str) -> tuple[str, bool]:
    updated = value.replace("Client: 716 HT", "Client: 716 Menzah6")
    return updated, updated != value


def process_csv(stats: UpdateStats) -> None:
    rows: list[dict[str, str]] = []
    with CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            row_changed = False

            client = row.get("client")
            address = row.get("address")
            normalized_client = normalize_client(client, address)
            if normalized_client != client:
                row["client"] = normalized_client or ""
                stats.client_updates += 1
                row_changed = True

            searchable_text = row.get("searchable_text", "")
            updated_searchable_text, text_changed = normalize_searchable_text(searchable_text)
            if text_changed:
                row["searchable_text"] = updated_searchable_text
                stats.searchable_text_updates += 1
                row_changed = True

            raw_payload = row.get("raw_payload", "")
            if raw_payload:
                payload = json.loads(raw_payload)
                if walk_json(payload, stats):
                    row["raw_payload"] = json.dumps(payload, ensure_ascii=False)
                    row_changed = True

            rows.append(row)
            if row_changed:
                stats.csv_rows_changed += 1

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    stats = UpdateStats()
    process_json_files(stats)
    process_csv(stats)
    export_unique_values()
    print(
        json.dumps(
            {
                "json_files_changed": stats.json_files_changed,
                "csv_rows_changed": stats.csv_rows_changed,
                "client_updates": stats.client_updates,
                "searchable_text_updates": stats.searchable_text_updates,
                "unique_values_exported": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
