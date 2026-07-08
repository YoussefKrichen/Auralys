from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.normalize import load_fiches_from_file, maybe_fix_text


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "data" / "processed" / "knowledge_base_txt"
SOURCE_FILES = [
    ROOT_DIR / "data" / "raw_json" / "AROMAIR_Rapport_Detaille_Confusion.docx",
    ROOT_DIR / "data" / "raw_json" / "output_json.json",
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for source_path in SOURCE_FILES:
        fiches = load_fiches_from_file(source_path)
        content = render_source_text(source_path, fiches)
        output_path = OUTPUT_DIR / f"{source_path.stem}.txt"
        output_path.write_text(content, encoding="utf-8")
    print(f"Exported {len(SOURCE_FILES)} TXT files to {OUTPUT_DIR}")


def render_source_text(source_path: Path, fiches: list) -> str:
    lines: list[str] = []
    lines.append(f"Source: {source_path.name}")
    lines.append("")

    for index, fiche in enumerate(fiches, start=1):
        raw_payload = fiche.raw_payload or {}
        title = clean_text(raw_payload.get("question")) or fiche.page_key
        answer = clean_text(raw_payload.get("answer"))
        category = clean_text(raw_payload.get("category"))

        lines.append(f"Entry {index}")
        lines.append("-" * len(f"Entry {index}"))
        lines.append(f"Title: {title}")
        if category:
            lines.append(f"Category: {category}")
        if answer:
            lines.append("")
            lines.append(answer)
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    raw_text = str(value).strip()
    text = maybe_fix_text(raw_text) or repair_mojibake(raw_text) or raw_text
    text = text.strip()
    return text or None


def repair_mojibake(value: str) -> str | None:
    if not any(marker in value for marker in ("Ã", "â", "€™", "€", "œ")):
        return None
    try:
        return value.encode("latin1").decode("utf-8").strip()
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None


if __name__ == "__main__":
    main()
