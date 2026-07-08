from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "rapport_auralys.md"
DEFAULT_OUTPUT = ROOT / "docs" / "rapport_auralys.pdf"


def build_pdf(
    source: Path = DEFAULT_SOURCE,
    output: Path = DEFAULT_OUTPUT,
    title: str = "Rapport Application Auralys",
) -> Path:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleAuralys",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#16324F"),
        spaceAfter=12,
        alignment=TA_LEFT,
    )
    h2_style = ParagraphStyle(
        "HeadingAuralys",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1F4E79"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyAuralys",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        spaceAfter=6,
    )

    story = []
    bullet_buffer: list[ListItem] = []

    def flush_bullets() -> None:
        nonlocal bullet_buffer
        if not bullet_buffer:
            return
        story.append(
            ListFlowable(
                bullet_buffer,
                bulletType="bullet",
                leftIndent=16,
                bulletFontName="Helvetica",
                bulletFontSize=10,
            )
        )
        story.append(Spacer(1, 0.2 * cm))
        bullet_buffer = []

    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            flush_bullets()
            story.append(Spacer(1, 0.12 * cm))
            continue
        if line.startswith("# "):
            flush_bullets()
            story.append(Paragraph(_escape(line[2:]), title_style))
            continue
        if line.startswith("## "):
            flush_bullets()
            story.append(Paragraph(_escape(line[3:]), h2_style))
            continue
        if line.startswith("- "):
            bullet_buffer.append(ListItem(Paragraph(_escape(line[2:]), body_style)))
            continue
        flush_bullets()
        story.append(Paragraph(_escape(line), body_style))

    flush_bullets()

    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=title,
        author="OpenAI Codex",
    )
    doc.build(story)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a PDF report from a simple Markdown file.")
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Path to the markdown source file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the PDF output file.",
    )
    parser.add_argument(
        "--title",
        default="Rapport Application Auralys",
        help="PDF metadata title.",
    )
    return parser.parse_args()


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


if __name__ == "__main__":
    args = parse_args()
    output = build_pdf(source=args.source, output=args.output, title=args.title)
    print(output)
