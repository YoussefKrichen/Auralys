from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ingestion.export_unique_values import collect_unique_values


def main() -> None:
    payload = collect_unique_values()
    clients = payload["clients"]

    json_output = REPO_ROOT / "data/client_names_list.json"
    txt_output = REPO_ROOT / "data/client_names_list.txt"

    json_output.write_text(
        json.dumps(
            {
                "source_dir": payload["source_dir"],
                "count": len(clients),
                "clients": clients,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    txt_output.write_text("\n".join(clients) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "count": len(clients),
                "json_output": str(json_output.relative_to(REPO_ROOT)),
                "txt_output": str(txt_output.relative_to(REPO_ROOT)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
