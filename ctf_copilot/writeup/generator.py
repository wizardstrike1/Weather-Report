"""Generate Markdown + HTML writeups from persisted project state."""
from __future__ import annotations

import html
import re
from pathlib import Path

from ..core.project import Project
from .templates import HTML_TEMPLATE, MARKDOWN_TEMPLATE


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "_None recorded._"


def _md_to_html(md: str) -> str:
    """Minimal Markdown→HTML (headings, code fences, lists). Good enough for a
    self-contained report without adding a markdown dependency."""
    out, in_code = [], False
    for line in md.splitlines():
        if line.startswith("```"):
            out.append("<pre><code>" if not in_code else "</code></pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(line))
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("- "):
            out.append(f"<li>{html.escape(line[2:])}</li>")
        else:
            out.append(f"<p>{html.escape(line)}</p>" if line.strip() else "")
    return "\n".join(out)


def generate(project: Project) -> dict[str, Path]:
    st = project.state
    snap = st.snapshot(max_items=50)

    flags = [r["value"] for r in st.flag_candidates() if r["submitted"]]
    best_flag = flags[0] if flags else (
        snap["flag_candidates"][0]["value"] if snap["flag_candidates"] else "<unsolved>"
    )

    commands = "\n".join(
        f'$ {r["argv"]}\n{r["summary"][:500]}'
        for r in st.tool_outputs(limit=30)
    ) or "(no tools run)"

    outputs = "\n".join(
        o["summary"][:300] for o in snap["tool_outputs"]
    ) or "(none)"

    md = MARKDOWN_TEMPLATE.format(
        name=project.name,
        category=project.category or "unknown",
        difficulty=st.get_meta("difficulty", "unknown"),
        url=project.url or "n/a",
        status=st.get_meta("status", "unsolved"),
        summary=st.get_meta("writeup_summary",
                            "Solved with Weather Report." if project.solved
                            else "Investigation in progress."),
        enumeration=_bullets([r["summary"] for r in st.recent_actions(30)][::-1]),
        insight=st.get_meta("writeup_insight", "_See notes/hypotheses below._"),
        steps=_bullets(snap["hypotheses"] + [n["content"] for n in st.notes("note")]),
        commands=commands,
        outputs=outputs,
        flag=best_flag,
        lessons=st.get_meta("writeup_lessons", "_TODO: add lessons learned._"),
        repro="\n".join(
            f"- {r['path']} (sha256 {r['sha256'][:16]}…)" for r in st.downloads()
        ) or "_No downloaded artifacts._",
        artifacts=_bullets(
            [str(p.relative_to(project.root))
             for p in sorted(project.root.rglob("*"))
             if p.is_file() and p.suffix in {".png", ".bin", ".txt", ".log"}][:40]
        ),
    )

    md_path = project.root / "writeup.md"
    html_path = project.root / "writeup.html"
    md_path.write_text(md, "utf-8")
    html_path.write_text(
        HTML_TEMPLATE.format(name=html.escape(project.name), body=_md_to_html(md)),
        "utf-8",
    )
    # TODO: optional PDF via weasyprint/reportlab if installed; Markdown+HTML
    # are always produced.
    return {"markdown": md_path, "html": html_path}
