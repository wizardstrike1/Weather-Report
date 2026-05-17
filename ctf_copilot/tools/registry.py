"""Data-driven CTF tool registry.

Each tool is a declarative ``ToolSpec``. Adding a tool is a data change, not a
code change. The command template uses ``{placeholders}`` filled from validated
args by the sandbox; templates never go through a shell.

``noisy`` tools require explicit user approval before running.
``requires_target`` tools take a network target validated against allowed
domains. Tools are detected at runtime via ``shutil.which`` + configured paths.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from enum import Enum


class Category(str, Enum):
    SHELL = "shell"
    WEB = "web"
    FORENSICS = "forensics"
    STEGO = "stego"
    CRYPTO = "crypto"
    REVERSE = "reverse"
    PWN = "pwn"
    OSINT = "osint"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    category: Category
    binary: str
    # argv template; tokens like {file} {target} {wordlist} {arg} get substituted
    template: list[str]
    description: str
    install: dict[str, str] = field(default_factory=dict)  # os -> hint
    noisy: bool = False
    requires_target: bool = False
    optional: bool = True
    expensive: bool = False  # only available when max_tools_mode is ON


def _t(*parts: str) -> list[str]:
    return list(parts)


# --- the catalogue ---------------------------------------------------------
SPECS: list[ToolSpec] = [
    # shell / general
    ToolSpec("file", Category.SHELL, "file", _t("file", "{file}"),
             "Identify file type by magic bytes",
             {"linux": "apt install file", "macos": "brew install libmagic"},
             optional=False),
    ToolSpec("strings", Category.SHELL, "strings", _t("strings", "-a", "-n", "4", "{file}"),
             "Extract printable strings",
             {"linux": "apt install binutils", "macos": "brew install binutils"}),
    ToolSpec("xxd", Category.SHELL, "xxd", _t("xxd", "{file}"), "Hex dump",
             {"linux": "apt install xxd"}),
    ToolSpec("hexdump", Category.SHELL, "hexdump", _t("hexdump", "-C", "{file}"),
             "Canonical hex dump", {"linux": "apt install bsdmainutils"}),
    ToolSpec("python", Category.SHELL, "python", _t("python", "{file}"),
             "Run a Python script that exists in the project workspace. "
             "Accepts optional args.stdin (fed to stdin) and args.script_args "
             "(extra argv). Use with file.write to author + run solve scripts.",
             {"linux": "apt install python3", "macos": "brew install python"},
             optional=False),
    ToolSpec("python3", Category.SHELL, "python3", _t("python3", "{file}"),
             "Same as 'python' but the python3 binary.",
             {"linux": "apt install python3"}, optional=False),
    ToolSpec("rg", Category.SHELL, "rg", _t("rg", "-a", "{arg}", "{file}"),
             "Recursive regex search",
             {"linux": "apt install ripgrep", "macos": "brew install ripgrep"}),
    ToolSpec("jq", Category.SHELL, "jq", _t("jq", "{arg}", "{file}"),
             "JSON processor", {"linux": "apt install jq", "macos": "brew install jq"}),
    ToolSpec("7z", Category.SHELL, "7z", _t("7z", "x", "-y", "{file}"),
             "7-Zip extract", {"linux": "apt install p7zip-full"}),
    ToolSpec("foremost", Category.FORENSICS, "foremost", _t("foremost", "-i", "{file}", "-o", "{outdir}"),
             "File carving by header/footer", {"linux": "apt install foremost"}),
    ToolSpec("bulk_extractor", Category.FORENSICS, "bulk_extractor",
             _t("bulk_extractor", "-o", "{outdir}", "{file}"),
             "Bulk feature extraction", {"linux": "apt install bulk-extractor"}),

    # web
    ToolSpec("curl", Category.WEB, "curl", _t("curl", "-sS", "-i", "{target}"),
             "HTTP client", {"linux": "apt install curl"}, requires_target=True,
             optional=False),
    ToolSpec("httpie", Category.WEB, "http", _t("http", "--print=Hh", "{target}"),
             "Friendly HTTP client", {"linux": "pipx install httpie"},
             requires_target=True),
    ToolSpec("ffuf", Category.WEB, "ffuf",
             _t("ffuf", "-u", "{target}", "-w", "{wordlist}", "-mc", "200,301,302,403"),
             "Web fuzzer", {"linux": "go install github.com/ffuf/ffuf/v2@latest"},
             noisy=True, requires_target=True),
    ToolSpec("gobuster", Category.WEB, "gobuster",
             _t("gobuster", "dir", "-u", "{target}", "-w", "{wordlist}"),
             "Directory brute force", {"linux": "apt install gobuster"},
             noisy=True, requires_target=True),
    ToolSpec("feroxbuster", Category.WEB, "feroxbuster",
             _t("feroxbuster", "-u", "{target}", "-w", "{wordlist}"),
             "Recursive content discovery", {"linux": "apt install feroxbuster"},
             noisy=True, requires_target=True),
    ToolSpec("nikto", Category.WEB, "nikto", _t("nikto", "-h", "{target}"),
             "Web server scanner", {"linux": "apt install nikto"},
             noisy=True, requires_target=True),
    ToolSpec("sqlmap", Category.WEB, "sqlmap",
             _t("sqlmap", "-u", "{target}", "--batch", "--level=1"),
             "SQL injection tool (authorized CTF targets only)",
             {"linux": "apt install sqlmap"}, noisy=True, requires_target=True),
    ToolSpec("wafw00f", Category.WEB, "wafw00f", _t("wafw00f", "{target}"),
             "WAF fingerprint", {"linux": "pipx install wafw00f"},
             requires_target=True),
    ToolSpec("nuclei", Category.WEB, "nuclei", _t("nuclei", "-u", "{target}", "-silent"),
             "Template scanner (disabled unless templates installed)",
             {"linux": "go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"},
             noisy=True, requires_target=True),

    # forensics
    ToolSpec("binwalk", Category.FORENSICS, "binwalk", _t("binwalk", "-e", "{file}"),
             "Firmware/embedded file analysis", {"linux": "apt install binwalk"}),
    ToolSpec("exiftool", Category.FORENSICS, "exiftool", _t("exiftool", "{file}"),
             "Metadata reader", {"linux": "apt install libimage-exiftool-perl"}),
    ToolSpec("tshark", Category.FORENSICS, "tshark", _t("tshark", "-r", "{file}", "-q", "-z", "io,phs"),
             "PCAP analysis", {"linux": "apt install tshark"}),
    ToolSpec("tcpdump", Category.FORENSICS, "tcpdump", _t("tcpdump", "-nr", "{file}"),
             "PCAP reader", {"linux": "apt install tcpdump"}),
    ToolSpec("pdfinfo", Category.FORENSICS, "pdfinfo", _t("pdfinfo", "{file}"),
             "PDF metadata", {"linux": "apt install poppler-utils"}),
    ToolSpec("qpdf", Category.FORENSICS, "qpdf", _t("qpdf", "--show-encryption", "{file}"),
             "PDF transform", {"linux": "apt install qpdf"}),
    ToolSpec("volatility3", Category.FORENSICS, "vol",
             _t("vol", "-f", "{file}", "windows.info"),
             "Memory forensics", {"linux": "pipx install volatility3"}),

    # stego
    ToolSpec("steghide", Category.STEGO, "steghide",
             _t("steghide", "extract", "-sf", "{file}", "-p", "{arg}"),
             "JPEG/WAV stego", {"linux": "apt install steghide"}),
    ToolSpec("zsteg", Category.STEGO, "zsteg", _t("zsteg", "-a", "{file}"),
             "PNG/BMP LSB stego", {"linux": "gem install zsteg"}),
    ToolSpec("stegseek", Category.STEGO, "stegseek", _t("stegseek", "{file}", "{wordlist}"),
             "Fast steghide cracker",
             {"linux": "https://github.com/RickdeJager/stegseek"}),
    ToolSpec("pngcheck", Category.STEGO, "pngcheck", _t("pngcheck", "-v", "{file}"),
             "PNG integrity", {"linux": "apt install pngcheck"}),
    ToolSpec("outguess", Category.STEGO, "outguess",
             _t("outguess", "-r", "{file}", "{outfile}"),
             "Outguess stego", {"linux": "apt install outguess"}),

    # crypto
    ToolSpec("openssl", Category.CRYPTO, "openssl", _t("openssl", "{arg}"),
             "Crypto toolkit", {"linux": "apt install openssl"}, optional=False),
    ToolSpec("john", Category.CRYPTO, "john", _t("john", "{file}"),
             "Password cracker", {"linux": "apt install john"}),
    ToolSpec("hashcat", Category.CRYPTO, "hashcat",
             _t("hashcat", "-m", "{arg}", "{file}", "{wordlist}"),
             "GPU password cracker", {"linux": "apt install hashcat"}),
    ToolSpec("name-that-hash", Category.CRYPTO, "nth", _t("nth", "-t", "{arg}"),
             "Hash identifier", {"linux": "pipx install name-that-hash"}),
    ToolSpec("RsaCtfTool", Category.CRYPTO, "RsaCtfTool",
             _t("RsaCtfTool", "{arg}"),
             "RSA attack toolkit (weak/known-key recovery). Pass args via "
             "{arg}, e.g. '--publickey key.pub --uncipher cipher.txt'",
             {"linux": "pipx install RsaCtfTool"}),
    ToolSpec("ciphey", Category.CRYPTO, "ciphey", _t("ciphey", "-t", "{arg}"),
             "Auto-decrypt/decode unknown ciphertext",
             {"linux": "pipx install ciphey"}),
    ToolSpec("ares", Category.CRYPTO, "ares", _t("ares", "-t", "{arg}"),
             "Auto-decrypt (ciphey successor)",
             {"linux": "cargo install project_ares"}),
    ToolSpec("sage", Category.CRYPTO, "sage", _t("sage", "{file}"),
             "SageMath script runner (advanced number theory). EXPENSIVE — "
             "needs Maximum tools mode.",
             {"linux": "apt install sagemath"}, expensive=True),

    # reverse
    ToolSpec("r2", Category.REVERSE, "r2", _t("r2", "-A", "-q", "-c", "{arg}", "{file}"),
             "radare2 reverse engineering", {"linux": "apt install radare2"}),
    ToolSpec("objdump", Category.REVERSE, "objdump", _t("objdump", "-d", "{file}"),
             "Disassembler", {"linux": "apt install binutils"}),
    ToolSpec("readelf", Category.REVERSE, "readelf", _t("readelf", "-a", "{file}"),
             "ELF reader", {"linux": "apt install binutils"}),
    ToolSpec("checksec", Category.PWN, "checksec", _t("checksec", "--file={file}"),
             "Binary hardening check", {"linux": "apt install checksec"}),
    ToolSpec("strace", Category.REVERSE, "strace", _t("strace", "-f", "{file}"),
             "Syscall trace", {"linux": "apt install strace"}),
    ToolSpec("ltrace", Category.REVERSE, "ltrace", _t("ltrace", "{file}"),
             "Library call trace", {"linux": "apt install ltrace"}),
    ToolSpec("jadx", Category.REVERSE, "jadx", _t("jadx", "-d", "{outdir}", "{file}"),
             "APK/dex to Java", {"linux": "apt install jadx"}),
    ToolSpec("apktool", Category.REVERSE, "apktool", _t("apktool", "d", "-f", "{file}", "-o", "{outdir}"),
             "APK disassembler", {"linux": "apt install apktool"}),
    ToolSpec("upx", Category.REVERSE, "upx", _t("upx", "-d", "{file}"),
             "Executable packer", {"linux": "apt install upx-ucl"}),
    ToolSpec("gdb", Category.REVERSE, "gdb",
             _t("gdb", "-q", "-batch", "-ex", "{arg}", "{file}"),
             "GDB batch command on a binary (one-shot). For INTERACTIVE "
             "debugging use the session.spawn action instead.",
             {"linux": "apt install gdb"}),
    ToolSpec("angr", Category.REVERSE, "angr", _t("angr", "{file}"),
             "Symbolic execution scaffold. EXPENSIVE — needs Maximum tools "
             "mode; prefer authoring an angr script via file.write+python.",
             {"linux": "pipx install angr"}, expensive=True),

    # pwn
    ToolSpec("pwn", Category.PWN, "pwn", _t("pwn", "{arg}"),
             "pwntools CLI (checksec/cyclic/disasm/shellcraft/elfdiff). For "
             "exploits, file.write a pwntools script then tool.run python.",
             {"linux": "pipx install pwntools"}),
    ToolSpec("seccomp-tools", Category.PWN, "seccomp-tools",
             _t("seccomp-tools", "dump", "{file}"),
             "Dump seccomp BPF rules from a binary",
             {"linux": "gem install seccomp-tools"}),
    ToolSpec("ROPgadget", Category.PWN, "ROPgadget", _t("ROPgadget", "--binary", "{file}"),
             "ROP gadget finder", {"linux": "pipx install ROPgadget"}),
    ToolSpec("ropper", Category.PWN, "ropper", _t("ropper", "-f", "{file}"),
             "ROP gadget finder", {"linux": "pipx install ropper"}),
    ToolSpec("patchelf", Category.PWN, "patchelf", _t("patchelf", "{arg}", "{file}"),
             "ELF interpreter patcher", {"linux": "apt install patchelf"}),
    ToolSpec("one_gadget", Category.PWN, "one_gadget", _t("one_gadget", "{file}"),
             "libc one-gadget finder", {"linux": "gem install one_gadget"}),

    # osint
    ToolSpec("whois", Category.OSINT, "whois", _t("whois", "{target}"),
             "Domain registration", {"linux": "apt install whois"}, requires_target=True),
    ToolSpec("dig", Category.OSINT, "dig", _t("dig", "{target}", "ANY"),
             "DNS lookup", {"linux": "apt install dnsutils"}, requires_target=True),
    ToolSpec("nslookup", Category.OSINT, "nslookup", _t("nslookup", "{target}"),
             "DNS lookup", {"linux": "apt install dnsutils"}, requires_target=True),
]

# TODO: Ghidra/Burp/ZAP/wireshark/sonic-visualiser are GUI launchers — add a
# separate "launcher" mechanism that opens them on the user's machine rather
# than capturing stdout. theHarvester/sherlock/RsaCtfTool/sage/pwntools are
# library/long-running; wire dedicated wrappers with their own arg schemas.

BY_NAME: dict[str, ToolSpec] = {s.name: s for s in SPECS}


class ToolRegistry:
    def __init__(self, tool_paths: dict[str, str] | None = None,
                 max_tools: bool = False) -> None:
        self._paths = tool_paths or {}
        # when False, expensive specs are hidden and refused
        self._max_tools = max_tools

    def resolve_binary(self, spec: ToolSpec) -> str | None:
        if spec.name in self._paths:
            return self._paths[spec.name]
        return shutil.which(spec.binary)

    def _gated(self, spec: ToolSpec | None) -> bool:
        """True if the spec is hidden because it's expensive and the
        Maximum-tools toggle is off."""
        return bool(spec and spec.expensive and not self._max_tools)

    def is_available(self, name: str) -> bool:
        spec = BY_NAME.get(name)
        if spec is None or self._gated(spec):
            return False
        return bool(self.resolve_binary(spec))

    def get(self, name: str) -> ToolSpec | None:
        spec = BY_NAME.get(name)
        return None if self._gated(spec) else spec

    def availability(self) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        for spec in SPECS:
            gated = self._gated(spec)
            out.append(
                {
                    "name": spec.name,
                    "category": spec.category.value,
                    # gated expensive tools report unavailable so the solver
                    # never offers them; the GUI can still show them locked.
                    "available": (not gated) and bool(self.resolve_binary(spec)),
                    "noisy": spec.noisy,
                    "expensive": spec.expensive,
                    "locked": gated,
                    "description": spec.description,
                    "install": spec.install,
                }
            )
        return out
