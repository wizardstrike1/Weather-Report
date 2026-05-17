"""Dependency-free built-in analysis so the app is useful even with no tools.

Everything here is pure-Python and safe (no subprocess, bounded resource use).
"""
from __future__ import annotations

import math
import re
import zipfile
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

# (offset, magic bytes, label)
_MAGIC: list[tuple[int, bytes, str]] = [
    (0, b"\x7fELF", "ELF executable"),
    (0, b"MZ", "DOS/PE executable"),
    (0, b"\x89PNG\r\n\x1a\n", "PNG image"),
    (0, b"\xff\xd8\xff", "JPEG image"),
    (0, b"GIF8", "GIF image"),
    (0, b"%PDF", "PDF document"),
    (0, b"PK\x03\x04", "ZIP / Office / JAR / APK"),
    (0, b"\x1f\x8b", "gzip"),
    (0, b"BZh", "bzip2"),
    (0, b"\xfd7zXZ\x00", "xz"),
    (0, b"7z\xbc\xaf\x27\x1c", "7-Zip"),
    (0, b"Rar!", "RAR archive"),
    (0, b"\xd4\xc3\xb2\xa1", "pcap (LE)"),
    (0, b"\xa1\xb2\xc3\xd4", "pcap (BE)"),
    (0, b"\n\r\r\n", "pcapng"),
    (0, b"OggS", "Ogg media"),
    (0, b"RIFF", "RIFF (WAV/AVI)"),
    (0, b"ID3", "MP3 (ID3)"),
    (0, b"SQLite format 3\x00", "SQLite database"),
]

DEFAULT_FLAG_RE = re.compile(rb"[A-Za-z0-9_]{2,16}\{[^}\r\n]{1,256}\}")
PRINTABLE = set(range(0x20, 0x7F)) | {0x09, 0x0A, 0x0D}


@dataclass
class AnalysisResult:
    path: str
    size: int
    file_type: str
    entropy: float
    sha256: str
    strings_sample: list[str] = field(default_factory=list)
    hex_preview: str = ""
    flag_candidates: list[str] = field(default_factory=list)
    extracted: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"file={self.path} size={self.size}B type={self.file_type}",
            f"entropy={self.entropy:.2f} sha256={self.sha256[:16]}…",
        ]
        if self.flag_candidates:
            lines.append("flags=" + ", ".join(self.flag_candidates[:5]))
        if self.extracted:
            lines.append(f"extracted {len(self.extracted)} file(s)")
        if self.strings_sample:
            lines.append("strings: " + " | ".join(self.strings_sample[:8]))
        lines += self.notes
        return "\n".join(lines)


def identify(data: bytes) -> str:
    for off, magic, label in _MAGIC:
        if data[off : off + len(magic)] == magic:
            return label
    if data and all(b in PRINTABLE for b in data[:512]):
        return "ASCII/UTF-8 text"
    return "unknown / raw binary"


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    freq = [0] * 256
    for b in data:
        freq[b] += 1
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in freq if c)


def extract_strings(data: bytes, min_len: int = 4, limit: int = 400) -> list[str]:
    out: list[str] = []
    cur = bytearray()
    for b in data:
        if 0x20 <= b < 0x7F:
            cur.append(b)
        else:
            if len(cur) >= min_len:
                out.append(cur.decode("ascii", "ignore"))
                if len(out) >= limit:
                    break
            cur.clear()
    if len(cur) >= min_len and len(out) < limit:
        out.append(cur.decode("ascii", "ignore"))
    return out


def hex_preview(data: bytes, nbytes: int = 256) -> str:
    chunk = data[:nbytes]
    lines = []
    for i in range(0, len(chunk), 16):
        row = chunk[i : i + 16]
        hexs = " ".join(f"{b:02x}" for b in row)
        ascii_ = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in row)
        lines.append(f"{i:08x}  {hexs:<47}  {ascii_}")
    return "\n".join(lines)


def find_flags(data: bytes, pattern: re.Pattern[bytes] | None = None) -> list[str]:
    rx = pattern or DEFAULT_FLAG_RE
    seen: list[str] = []
    for m in rx.finditer(data):
        s = m.group().decode("ascii", "ignore")
        if s not in seen:
            seen.append(s)
    return seen


def _safe_extract_zip(path: Path, dest: Path, max_files: int, max_bytes: int) -> list[str]:
    out: list[str] = []
    total = 0
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist()[:max_files]:
            name = Path(info.filename).name  # flatten — defeat path traversal
            if not name:
                continue
            total += info.file_size
            if total > max_bytes:
                out.append("[extraction stopped: size limit]")
                break
            target = dest / name
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
            out.append(str(target))
    return out


def _safe_extract_tar(path: Path, dest: Path, max_files: int) -> list[str]:
    out: list[str] = []
    with tarfile.open(path) as tf:
        for member in tf.getmembers()[:max_files]:
            if not member.isfile():
                continue
            name = Path(member.name).name
            data = tf.extractfile(member)
            if data is None:
                continue
            target = dest / name
            target.write_bytes(data.read())
            out.append(str(target))
    return out


def analyze(
    path: str | Path,
    *,
    flag_pattern: re.Pattern[bytes] | None = None,
    extract_to: Path | None = None,
    read_limit: int = 8 * 1024 * 1024,
    max_extract_files: int = 200,
    max_extract_bytes: int = 200 * 1024 * 1024,
) -> AnalysisResult:
    import hashlib

    p = Path(path)
    raw = p.read_bytes()
    data = raw[:read_limit]

    res = AnalysisResult(
        path=str(p),
        size=p.stat().st_size,
        file_type=identify(data),
        entropy=round(shannon_entropy(data), 4),
        sha256=hashlib.sha256(raw).hexdigest(),
        strings_sample=extract_strings(data)[:50],
        hex_preview=hex_preview(data),
        flag_candidates=find_flags(raw, flag_pattern),
    )

    if res.entropy > 7.5:
        res.notes.append("high entropy — likely encrypted/compressed/packed")

    if extract_to is not None:
        try:
            extract_to.mkdir(parents=True, exist_ok=True)
            if zipfile.is_zipfile(p):
                res.extracted = _safe_extract_zip(
                    p, extract_to, max_extract_files, max_extract_bytes
                )
            elif tarfile.is_tarfile(p):
                res.extracted = _safe_extract_tar(p, extract_to, max_extract_files)
        except Exception as e:  # extraction must never crash analysis
            res.notes.append(f"extraction failed: {e}")

    # optional richer inspection
    try:
        if res.file_type.startswith(("PNG", "JPEG", "GIF")):
            from PIL import Image  # type: ignore

            with Image.open(p) as im:
                res.notes.append(
                    f"image {im.size[0]}x{im.size[1]} mode={im.mode}"
                )
    except Exception:
        pass
    try:
        if res.file_type.startswith("pcap"):
            from scapy.all import rdpcap  # type: ignore

            pkts = rdpcap(str(p))
            res.notes.append(f"pcap: {len(pkts)} packets")
    except Exception:
        pass

    return res
