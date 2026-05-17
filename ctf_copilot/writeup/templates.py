"""Writeup templates. Markdown is the source of truth; HTML wraps it."""
from __future__ import annotations

MARKDOWN_TEMPLATE = """\
# {name}

- **Category:** {category}
- **Difficulty:** {difficulty}
- **Target:** {url}
- **Status:** {status}

## Summary
{summary}

## Enumeration
{enumeration}

## Vulnerability / Insight
{insight}

## Solving Steps
{steps}

## Commands Run
```
{commands}
```

## Important Outputs
```
{outputs}
```

## Flag
```
{flag}
```

## Lessons Learned
{lessons}

## Reproducibility Notes
{repro}

## Artifacts
{artifacts}
"""

HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{name}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;
padding:0 1rem;line-height:1.5}}pre{{background:#1e1e1e;color:#eee;padding:1rem;
overflow:auto;border-radius:6px}}code{{font-family:ui-monospace,monospace}}
h1,h2{{border-bottom:1px solid #ddd;padding-bottom:.2rem}}</style></head>
<body>{body}</body></html>
"""
