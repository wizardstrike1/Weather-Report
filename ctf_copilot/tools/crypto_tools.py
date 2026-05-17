"""Pure-Python crypto helpers used by the built-in analyzer and the LLM via
the ``file.extract`` action. All bounded, no network, no subprocess.
"""
from __future__ import annotations

import base64
import binascii
import codecs
import string
from urllib.parse import unquote

PRINTABLE = set(bytes(string.printable, "ascii"))


def _printable_ratio(b: bytes) -> float:
    return sum(1 for x in b if x in PRINTABLE) / len(b) if b else 0.0


def try_base_decodings(s: str) -> dict[str, str]:
    """Attempt base64/32/16/85 + hex; keep results that look like text."""
    out: dict[str, str] = {}
    raw = s.strip().encode()
    attempts = {
        "base64": lambda: base64.b64decode(raw, validate=False),
        "base32": lambda: base64.b32decode(raw + b"=" * (-len(raw) % 8)),
        "base16": lambda: base64.b16decode(raw, casefold=True),
        "ascii85": lambda: base64.a85decode(raw),
        "base85": lambda: base64.b85decode(raw),
        "hex": lambda: binascii.unhexlify(raw.strip()),
    }
    for name, fn in attempts.items():
        try:
            dec = fn()
            if dec and _printable_ratio(dec) > 0.85:
                out[name] = dec.decode("utf-8", "replace")
        except (binascii.Error, ValueError):
            continue
    if (u := unquote(s)) != s:
        out["urldecode"] = u
    return out


def rot_bruteforce(s: str) -> dict[int, str]:
    res: dict[int, str] = {}
    for k in range(1, 26):
        out = []
        for ch in s:
            if ch.isupper():
                out.append(chr((ord(ch) - 65 + k) % 26 + 65))
            elif ch.islower():
                out.append(chr((ord(ch) - 97 + k) % 26 + 97))
            else:
                out.append(ch)
        res[k] = "".join(out)
    return res


def single_byte_xor(data: bytes) -> list[tuple[int, str, float]]:
    """Return (key, decoded, score) sorted best-first (English-ish heuristic)."""
    common = b" etaoinshrdluETAOIN"
    scored: list[tuple[int, str, float]] = []
    for key in range(256):
        dec = bytes(b ^ key for b in data)
        score = sum(1 for b in dec if b in common) / len(dec) if dec else 0
        if _printable_ratio(dec) > 0.9:
            scored.append((key, dec.decode("utf-8", "replace"), round(score, 3)))
    scored.sort(key=lambda t: t[2], reverse=True)
    return scored[:10]


def repeating_key_xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def identify_hash(s: str) -> list[str]:
    s = s.strip()
    n = len(s)
    is_hex = all(c in string.hexdigits for c in s)
    table = {32: ["MD5", "NTLM"], 40: ["SHA-1"], 56: ["SHA-224"],
             64: ["SHA-256"], 96: ["SHA-384"], 128: ["SHA-512"]}
    out = table.get(n, []) if is_hex else []
    if s.startswith("$2"):
        out.append("bcrypt")
    if s.startswith("$argon2"):
        out.append("argon2")
    if s.startswith(("$1$", "$5$", "$6$")):
        out.append("crypt(3)")
    return out or ["unknown"]


def caesar_vigenere_hint() -> str:
    return ("Use rot_bruteforce for Caesar. For Vigenère, recover the key with "
            "Kasiski/IC analysis, then repeating_key_xor-style subtraction. "
            "TODO: add full Vigenère + frequency-analysis solver.")
