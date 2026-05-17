# Security & Authorized-Use Policy

CTF Copilot is a **defensive / educational** tool for Capture-the-Flag
challenges **you are explicitly authorized to attempt** (a CTF you are
registered for, a lab you own, or a target the organizer has put in scope).

## Hard boundaries enforced in code

- **Allowed-domain allowlist.** Every browser navigation and every
  network-targeting tool is validated by `core/permissions.py`. With an empty
  allowlist, *all* network actions are denied. Subdomain matching is exact-
  suffix; look-alike domains (`notctf.example.attacker.com`) are rejected.
- **Workspace path sandbox.** Tool inputs/outputs are resolved and confined to
  the active project directory. Path traversal (`../`) and zip-slip are
  blocked (archive members are flattened to basenames on extraction).
- **No arbitrary shell.** The model cannot run free-form commands. Only
  registered `ToolSpec` templates execute, argv-only, `shell=False`. Unknown
  tools, unknown placeholders, and missing required args are rejected.
- **Strict action validation.** Claude's output must parse into a pydantic
  `LLMResponse`; anything else is refused before execution.
- **Approval gate.** Noisy/active tools (ffuf, gobuster, sqlmap, nikto,
  nuclei, feroxbuster) and any medium/high-risk or flag-submit action require
  explicit user approval in the UI. Auto-submit is off by default.
- **Rate limiting & timeouts** on the tool runner.

## Data handling

- The Anthropic API key is read only from the environment / `.env`. It is
  **never** written to `config.json` or project files.
- Cookie and `localStorage` **values** are withheld from the model by default
  (keys only). Screenshots are never sent unless you opt in.
- Full tool logs stay local; only truncated summaries go to the model.

## Your responsibilities

- Only add hosts you are authorized to test to the allowlist.
- `sqlmap`/`nuclei`/fuzzers against third-party infrastructure without
  authorization is illegal — the allowlist is a safety net, not permission.
- Review the approval prompts; they exist so a noisy scan never fires silently.

Report a security issue by opening a private advisory rather than a public
issue.
