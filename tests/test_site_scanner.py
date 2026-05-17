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


def test_competition_name():
    assert s.competition_name("PicoCTF 2025 - Challenges", "http://x") == \
        "PicoCTF 2025"
    assert s.competition_name("", "https://play.ctf.example/x") == \
        "play.ctf.example"
