from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

import markdown


ROOT = Path(__file__).resolve().parents[1]


def split_segments(source: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"```(?P<lang>[^\n`]*)\n(?P<body>.*?)```", re.DOTALL)
    segments: list[tuple[str, str]] = []
    cursor = 0
    for match in pattern.finditer(source):
        if match.start() > cursor:
            segments.append(("markdown", source[cursor:match.start()]))
        language = match.group("lang").strip().lower()
        body = match.group("body").strip("\n")
        segments.append((language or "code", body))
        cursor = match.end()
    if cursor < len(source):
        segments.append(("markdown", source[cursor:]))
    return segments


def render_segment(kind: str, body: str) -> str:
    if kind == "markdown":
        if not body.strip():
            return ""
        return markdown.markdown(
            body,
            extensions=["extra", "sane_lists", "tables"],
            output_format="html5",
        )
    if kind == "mermaid":
        return f'<section class="diagram-shell"><pre class="mermaid">{html.escape(body)}</pre></section>'
    escaped = html.escape(body)
    return f'<pre class="code-block"><code>{escaped}</code></pre>'


def build_html(source_path: Path, title: str) -> str:
    source = source_path.read_text(encoding="utf-8")
    rendered = "\n".join(render_segment(kind, body) for kind, body in split_segments(source))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #132033;
      --muted: #5f6b7b;
      --line: #d7dde5;
      --surface: #ffffff;
      --surface-soft: #f5f7fa;
      --navy: #0a2558;
      --accent: #2257b8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Aptos, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #eef2f6;
    }}
    .page {{
      width: min(1320px, calc(100% - 40px));
      margin: 24px auto 40px;
      padding: 36px 42px;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: 0 24px 60px rgba(20, 32, 51, 0.08);
    }}
    h1, h2, h3 {{
      color: var(--navy);
      letter-spacing: -0.02em;
      break-after: avoid-page;
    }}
    h1 {{
      font-size: 2rem;
      margin: 0 0 18px;
      padding-bottom: 14px;
      border-bottom: 2px solid var(--line);
    }}
    h2 {{
      font-size: 1.3rem;
      margin-top: 30px;
      margin-bottom: 12px;
    }}
    h3 {{
      font-size: 1.05rem;
      margin-top: 20px;
      margin-bottom: 8px;
    }}
    p, li {{
      font-size: 0.98rem;
      line-height: 1.6;
    }}
    ul, ol {{
      padding-left: 20px;
    }}
    code {{
      padding: 0.12rem 0.35rem;
      border-radius: 6px;
      background: var(--surface-soft);
      font-family: Consolas, "Courier New", monospace;
      font-size: 0.92em;
    }}
    .code-block {{
      overflow-x: auto;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #0f1724;
      color: #f0f5ff;
    }}
    .diagram-shell {{
      overflow-x: auto;
      padding: 18px 20px;
      margin: 20px 0 24px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: linear-gradient(180deg, #fcfdff 0%, #f4f7fb 100%);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
      break-inside: avoid-page;
    }}
    .mermaid {{
      min-width: max-content;
      margin: 0;
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
      text-align: center;
    }}
    .diagram-shell .mermaid svg {{
      display: block;
      width: auto !important;
      max-width: none !important;
      height: auto;
      margin: 0 auto;
      overflow: visible;
    }}
    .diagram-shell .label,
    .diagram-shell .nodeLabel,
    .diagram-shell .edgeLabel {{
      line-height: 1.35;
    }}
    .diagram-shell .edgeLabel > foreignObject > div,
    .diagram-shell .label foreignObject > div {{
      padding: 2px 6px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.92);
      box-shadow: 0 1px 4px rgba(19, 32, 51, 0.08);
    }}
    .diagram-shell .cluster rect,
    .diagram-shell .node rect,
    .diagram-shell .node polygon,
    .diagram-shell .node path {{
      filter: drop-shadow(0 6px 14px rgba(19, 32, 51, 0.08));
    }}
    .diagram-shell .flowchart-link,
    .diagram-shell .messageLine0,
    .diagram-shell .messageLine1 {{
      stroke-width: 2.2px;
    }}
    .diagram-shell .arrowheadPath {{
      stroke-width: 1.4px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 14px 0;
    }}
    th, td {{
      padding: 10px 12px;
      border: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: var(--surface-soft);
    }}
    @media print {{
      body {{
        background: white;
      }}
      .page {{
        width: 100%;
        margin: 0;
        padding: 0;
        border: 0;
        border-radius: 0;
        box-shadow: none;
      }}
      .diagram-shell {{
        overflow: visible;
        padding: 12px 0;
        border-color: #d8dee8;
        box-shadow: none;
      }}
      .diagram-shell .mermaid svg {{
        max-width: 100% !important;
      }}
      h1, h2, h3, .diagram-shell {{
        break-inside: avoid-page;
      }}
    }}
    @media (max-width: 820px) {{
      .page {{
        width: calc(100% - 24px);
        padding: 22px 16px;
      }}
      .diagram-shell {{
        padding: 14px 12px;
        margin: 16px 0 20px;
      }}
    }}
  </style>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{
      startOnLoad: true,
      securityLevel: "loose",
      deterministicIds: true,
      theme: "base",
      themeVariables: {{
        primaryColor: "#e8f0ff",
        primaryTextColor: "#132033",
        primaryBorderColor: "#2854a0",
        lineColor: "#4c6387",
        secondaryColor: "#f5f7fa",
        tertiaryColor: "#ffffff",
        fontFamily: "Aptos, Segoe UI, sans-serif"
      }},
      flowchart: {{
        useMaxWidth: false,
        htmlLabels: true,
        curve: "monotoneX",
        nodeSpacing: 42,
        rankSpacing: 68,
        padding: 18,
        diagramPadding: 16,
        wrappingWidth: 180
      }},
      sequence: {{
        useMaxWidth: false,
        actorMargin: 60,
        width: 240,
        height: 80,
        boxMargin: 16,
        boxTextMargin: 8,
        noteMargin: 18,
        messageMargin: 44,
        mirrorActors: false
      }}
    }});
  </script>
</head>
<body>
  <main class="page">
    {rendered}
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Markdown with Mermaid fences to standalone HTML.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="Auralys Report")
    args = parser.parse_args()

    html_output = build_html(args.source, args.title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_output, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
