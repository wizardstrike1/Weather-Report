"""Scan a CTF site and enumerate challenges to bulk-create projects.

Two strategies, best-effort and ordered:
 1. CTFd JSON API (`/api/v1/challenges`) — by far the most common platform;
    uses the logged-in session cookies via the Playwright page.
 2. Generic heuristic over the page's links/text — categories and
    challenge-ish anchors.

The pure parsing/classification helpers are unit-tested; the live `scan()`
drives an existing PlaywrightSession.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

CATEGORY_KEYWORDS = {
    "web": ["web", "xss", "sqli", "ssrf", "http header", "cookie"],
    "pwn": ["pwn", "binary exploitation", "exploit", "overflow", "rop",
            "ret2", "shellcode", "libc", "gadget", "format string", "heap"],
    "crypto": ["crypto", "rsa", "aes", "cipher", "hash", "ecc"],
    "reverse": ["reverse", "rev", "re ", "disassembl", "decompil"],
    "forensics": ["forensic", "pcap", "memory", "disk", "stego-forensic"],
    "stego": ["steg", "stegano"],
    "osint": ["osint", "recon", "geoguess"],
    "misc": ["misc", "trivia", "warmup", "sanity", "welcome"],
}

_CHALLENGE_HREF = re.compile(
    r"/(challenge|challenges|task|tasks|chal|problem)s?(/|#|\?|$)", re.I
)
_ANCHOR_RE = re.compile(
    r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_TAGS_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ChallengeHit:
    name: str
    category: str
    url: str


def classify_category(*texts: str) -> str:
    blob = " ".join(t.lower() for t in texts if t)
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(k in blob for k in kws):
            return cat
    return "unknown"


def parse_ctfd(payload: dict, base_url: str) -> list[ChallengeHit]:
    """Parse a CTFd /api/v1/challenges response."""
    if not isinstance(payload, dict) or not payload.get("success"):
        return []
    origin = _origin(base_url)
    hits: list[ChallengeHit] = []
    for c in payload.get("data", []) or []:
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        cat = str(c.get("category", "")).strip() or classify_category(name)
        cid = c.get("id", "")
        hits.append(ChallengeHit(name, cat.lower(),
                                 f"{origin}/challenges#{cid}"))
    return hits


def extract_from_links(
    links: list[dict], page_text: str, base_url: str
) -> list[ChallengeHit]:
    """Heuristic fallback: anchors that look like challenges."""
    origin = _origin(base_url) if base_url else ""
    hits: list[ChallengeHit] = []
    for ln in links:
        href = (ln.get("href") or "").strip()
        text = (ln.get("text") or "").strip()
        if not href or not text or len(text) > 80:
            continue
        if not _CHALLENGE_HREF.search(href):
            continue
        if href.startswith("http"):
            url = href
        elif origin:
            url = urljoin(origin + "/", href)
        else:  # offline HTML with no base — keep the raw href
            url = href
        hits.append(ChallengeHit(text, classify_category(text), url))
    return hits


def dedupe(hits: list[ChallengeHit]) -> list[ChallengeHit]:
    seen: set[tuple[str, str]] = set()
    out: list[ChallengeHit] = []
    for h in hits:
        key = (h.name.lower(), h.url)
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out


def anchors_from_html(html: str) -> list[dict]:
    """Pull (text, href) pairs out of raw saved HTML (no browser)."""
    out: list[dict] = []
    for href, inner in _ANCHOR_RE.findall(html):
        text = re.sub(r"\s+", " ", _TAGS_RE.sub("", inner)).strip()
        out.append({"text": text, "href": href.strip()})
    return out


def scan_html(html: str, base_url: str = "") -> tuple[str, list[ChallengeHit]]:
    """Mode 3: parse a saved challenge-listing HTML file (offline)."""
    hits = extract_from_links(anchors_from_html(html), html, base_url or "")
    m = _TITLE_RE.search(html)
    title = re.sub(r"\s+", " ", _TAGS_RE.sub("", m.group(1))).strip() if m \
        else ""
    return competition_name(title, base_url or "imported.html"), dedupe(hits)


def _origin(url: str) -> str:
    p = urlparse(url if "://" in url else "http://" + url)
    return f"{p.scheme}://{p.netloc}"


def competition_name(title: str, url: str) -> str:
    title = (title or "").strip()
    if title and len(title) <= 60:
        # strip common suffixes like " - Challenges"
        return re.split(r"\s[-|–]\s", title)[0].strip()
    return urlparse(url if "://" in url else "http://" + url).netloc


def scan(session, base_url: str) -> tuple[str, list[ChallengeHit]]:
    """Drive a PlaywrightSession to enumerate challenges.

    Returns (competition_name, hits). Never raises for "nothing found".
    """
    obs = session.open_url(base_url)
    cur = obs.get("url", base_url)
    origin = _origin(cur)
    hits: list[ChallengeHit] = []

    # 1) CTFd API (same-origin fetch through the page; uses session cookies)
    try:
        data = session.fetch_json(f"{origin}/api/v1/challenges")
        if data:
            hits += parse_ctfd(data, origin)
    except Exception:
        pass

    # 2) heuristic over observed links + a /challenges page if linked
    if not hits:
        hits += extract_from_links(
            obs.get("links", []), obs.get("visible_text", ""), origin
        )
        if not hits:
            try:
                obs2 = session.open_url(f"{origin}/challenges")
                hits += extract_from_links(
                    obs2.get("links", []), obs2.get("visible_text", ""), origin
                )
            except Exception:
                pass

    comp = competition_name(obs.get("title", ""), cur)
    return comp, dedupe(hits)
