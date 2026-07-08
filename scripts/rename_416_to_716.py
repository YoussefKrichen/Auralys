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


CLIENT_PATTERN = re.compile(r"\b416\b")


@dataclass
class UpdateStats:
    json_files_changed: int = 0
    csv_rows_changed: int = 0
    client_updates: int = 0
    address_updates: int = 0
    signature_updates: int = 0


JSON_DIRECTORIES = (
    Path("data/raw_json"),
    Path("data/processed/maintenance"),
    Path("data/processed/Maintenance_json"),
)

CSV_PATH = Path("data/processed_csv/client_maintenance_form.csv")


def replace_client_name(value: str) -> tuple[str, bool]:
    updated = CLIENT_PATTERN.sub("716", value)
    return updated, updated != value


def replace_signature_text(value: str) -> tuple[str, bool]:
    updated = value.replace("The 416", "The 716")
    return updated, updated != value


def update_json_value(key: str, value: Any, stats: UpdateStats) -> tuple[Any, bool]:
    if not isinstance(value, str):
        return value, False

    if key == "client":
        updated, changed = replace_client_name(value)
        if changed:
            stats.client_updates += 1
        return updated, changed

    if key == "address" and value.strip() == "416":
        stats.address_updates += 1
        return "716", True

    if key == "text":
        updated, changed = replace_signature_text(value)
        if changed:
            stats.signature_updates += 1
        return updated, changed

    return value, False


def walk_json(payload: Any, stats: UpdateStats) -> bool:
    changed = False

    if isinstance(payload, dict):
        for key, value in list(payload.items()):
            updated, value_changed = update_json_value(key, value, stats)
            if value_changed:
                payload[key] = updated
                changed = True
                value = updated
            if isinstance(value, (dict, list)) and walk_json(value, stats):
                changed = True
        return changed

    if isinstance(payload, list):
        for item in payload:
            if walk_json(item, stats):
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


def update_searchable_text(value: str) -> tuple[str, bool]:
    updated = value
    updated = re.sub(r"(Client:\s*)416\b", r"\g<1>716", updated)
    updated = re.sub(r"(Address:\s*)416\b", r"\g<1>716", updated)
    updated = updated.replace("The 416", "The 716")
    return updated, updated != value


def process_csv(stats: UpdateStats) -> None:
    rows: list[dict[str, str]] = []
    with CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            row_changed = False

            client = row.get("client", "")
            updated_client, changed = replace_client_name(client)
            if changed:
                row["client"] = updated_client
                stats.client_updates += 1
                row_changed = True

            address = row.get("address", "")
            if address.strip() == "416":
                row["address"] = "716"
                stats.address_updates += 1
                row_changed = True

            signature = row.get("signature_text", "")
            updated_signature, changed = replace_signature_text(signature)
            if changed:
                row["signature_text"] = updated_signature
                stats.signature_updates += 1
                row_changed = True

            searchable_text = row.get("searchable_text", "")
            updated_searchable_text, changed = update_searchable_text(searchable_text)
            if changed:
                row["searchable_text"] = updated_searchable_text
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
                "address_updates": stats.address_updates,
                "signature_updates": stats.signature_updates,
                "unique_values_exported": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
