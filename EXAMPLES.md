# Example workflow — the bundled toy CTF

This walks the full MVP path end to end against a local target, so it works
with **no API key** (manual mode) and no external tools.

## 1. Serve the toy challenge

```bash
python examples/serve_toy_ctf.py
# -> Toy CTF on http://127.0.0.1:8000
```

It exposes `/` (an HTML page with a `flag{...}` in a comment and debug creds),
`/files/challenge.txt` (a downloadable file with a planted flag), and
`/robots.txt`.

## 2. Configure & launch

```bash
python -m ctf_copilot.app
```

- Settings (Ctrl+,) → **Allowed domains** → add `127.0.0.1` → Save.
  (Without this, navigation is correctly blocked — that's the safety net.)

## 3. Create the project

- Sidebar → **New challenge** → name it `toy`.
- Challenge tab → URL `http://127.0.0.1:8000/` → add context like
  *"web, flag format flag{...}"*.

## 4. Drive it

With an API key set, click **Auto-solve** and approve actions as prompted.
Without a key (manual mode), use the **Agent** tab to step through, or test
the pieces directly:

- The agent's `browser.open_url` produces a compact observation in the
  **Browser** log; the HTML-comment flag `flag{toy_html_comment_flag}` is
  picked up by the page flag scanner and appears in **Flag candidates**.
- A `browser.download` of `http://127.0.0.1:8000/files/challenge.txt` saves
  into `projects/toy/downloads/`, hashes it, and the built-in analyzer
  surfaces `flag{toy_downloaded_file_flag}`.
- A `tool.run` of `file` / `strings` on the download (if those binaries
  exist) shows in the **Tools** tab; full log under
  `projects/toy/tool_outputs/`.

## 5. Writeup

- **Writeup** tab → **Generate writeup now** → `projects/toy/writeup.md` and
  `writeup.html` are written and previewed; **Open HTML** opens the report.

## What this exercises

Playwright session ✦ compact page observation ✦ download interception ✦
built-in file analysis ✦ flag extraction ✦ SQLite project state ✦ writeup
generation ✦ permission allowlist ✦ manual-mode fallback — the full MVP
acceptance list.
