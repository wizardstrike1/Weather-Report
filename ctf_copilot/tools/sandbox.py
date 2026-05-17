"""Turn a ToolSpec + validated args into a safe argv.

No shell is ever used. Every ``{file}``/``{outdir}``/``{outfile}`` placeholder is
forced inside the workspace; every ``{target}`` is validated against allowed
domains. Unknown placeholders or unsupplied required args raise.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.permissions import PermissionDenied, Permissions
from .registry import ToolSpec

PATH_TOKENS = {"file", "outdir", "outfile", "wordlist"}


@dataclass
class BuiltCommand:
    argv: list[str]
    spec: ToolSpec
    cwd: Path


def build_command(
    spec: ToolSpec,
    binary: str,
    args: dict[str, str],
    perms: Permissions,
) -> BuiltCommand:
    argv: list[str] = []
    for i, token in enumerate(spec.template):
        if not (token.startswith("{") and token.endswith("}")):
            argv.append(binary if i == 0 else token)
            continue
        key = token[1:-1]
        if key not in args or args[key] == "":
            raise PermissionDenied(f"Tool {spec.name!r} requires argument {key!r}")
        value = str(args[key])

        if key in PATH_TOKENS:
            if key == "wordlist":
                # wordlists may live outside the workspace; require explicit
                # absolute path and existence, but do not force into workspace.
                p = Path(value)
                if not p.exists():
                    raise PermissionDenied(f"Wordlist not found: {p}")
                argv.append(str(p))
            elif key in ("outdir", "outfile"):
                argv.append(str(perms.resolve_in_workspace(value)))
            else:  # input file must exist inside workspace
                argv.append(str(perms.resolve_in_workspace(value, must_exist=True)))
        elif key == "target":
            argv.append(perms.check_network_target(value) if not spec.requires_target
                        else perms.check_url(value if "://" in value else "http://" + value))
        elif key == "arg":
            # free-form scalar arg (e.g. an openssl subcommand or a regex).
            # Passed as a single argv element — never shell-interpreted.
            argv.append(value)
        else:
            raise PermissionDenied(f"Unsupported placeholder {token!r} in {spec.name!r}")

    return BuiltCommand(argv=argv, spec=spec, cwd=perms.workspace)
