from ctf_copilot.core import site_scanner as s


def test_classify_category():
    assert s.classify_category("Baby RSA") == "crypto"
    assert s.classify_category("SQLi login bypass") == "web"
    assert s.classify_category("ret2libc") == "pwn"
    assert s.classify_category("totally generic title") == "unknown"


def test_parse_ctfd():
    payload = {
        "success": True,
        "data": [
            {"id": 1, "name": "Warmup", "category": "Misc"},
            {"id": 7, "name": "Crypt0", "category": "Crypto"},
            {"id": 9, "name": ""},  # skipped (no name)
        ],
    }
    hits = s.parse_ctfd(payload, "https://ctf.example/")
    assert len(hits) == 2
    assert hits[0].name == "Warmup" and hits[0].category == "misc"
    assert hits[1].url == "https://ctf.example/challenges#7"
    assert s.parse_ctfd({"success": False}, "x") == []


def test_extract_from_links_and_dedupe():
    links = [
        {"text": "Web 100", "href": "/challenges/web-100"},
        {"text": "Web 100", "href": "/challenges/web-100"},  # dup
        {"text": "Home", "href": "/"},                        # not a challenge
        {"text": "Pwn Me", "href": "https://x.ctf/task/3"},
    ]
    hits = s.dedupe(s.extract_from_links(links, "", "https://x.ctf/"))
    names = {h.name for h in hits}
    assert names == {"Web 100", "Pwn Me"}
    web = next(h for h in hits if h.name == "Web 100")
    assert web.url == "https://x.ctf/challenges/web-100"


def test_scan_html_offline():
    html = """
    <html><head><title>OpenCTF 2025 - Challenges</title></head><body>
      <a href="/challenges/web-1">Cookie Monster</a>
      <a href="https://o.ctf/task/42">RSA Warmup</a>
      <a href="/about">About</a>
      <a href="/challenges/web-1">Cookie Monster</a>
    </body></html>
    """
    comp, hits = s.scan_html(html, "https://o.ctf/")
    assert comp == "OpenCTF 2025"
    names = sorted(h.name for h in hits)
    assert names == ["Cookie Monster", "RSA Warmup"]
    cm = next(h for h in hits if h.name == "Cookie Monster")
    assert cm.url == "https://o.ctf/challenges/web-1"
    rsa = next(h for h in hits if h.name == "RSA Warmup")
    assert rsa.category == "crypto"


def test_scan_html_no_base_keeps_raw_href():
    html = '<a href="/challenges/c1">Pwnable</a>'
    _, hits = s.scan_html(html, "")
    assert hits[0].url == "/challenges/c1"
    assert hits[0].category == "pwn"


def test_competition_name():
    assert s.competition_name("PicoCTF 2025 - Challenges", "http://x") == \
        "PicoCTF 2025"
    assert s.competition_name("", "https://play.ctf.example/x") == \
        "play.ctf.example"
