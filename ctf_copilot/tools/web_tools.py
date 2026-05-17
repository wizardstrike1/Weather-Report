"""Lightweight web helpers. Network access here is *only* via the Playwright
session (so it inherits the browser profile and stays observable). robots.txt /
sitemap.xml fetches are scoped to the allowed domain by Permissions.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from ..core.permissions import Permissions

COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)


def interesting_from_html(html: str) -> dict[str, list[str]]:
    """Pull hidden inputs, comments and script srcs out of raw HTML.

    Used as a fallback summariser; the live page observer is preferred.
    """
    comments = [c.strip() for c in COMMENT_RE.findall(html) if c.strip()][:20]
    hidden = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*>', html, re.I)[:20]
    scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', html, re.I)[:20]
    links = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)[:50]
    return {
        "comments": comments,
        "hidden_inputs": hidden,
        "scripts": scripts,
        "links": links,
    }


def scoped_recon_urls(base_url: str, perms: Permissions) -> list[str]:
    """Return robots.txt / sitemap.xml URLs, validated against allowed domains.

    The caller fetches these *through the Playwright session*, not raw requests.
    """
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [urljoin(root + "/", p) for p in ("robots.txt", "sitemap.xml")]
    return [perms.check_url(u) for u in candidates]
