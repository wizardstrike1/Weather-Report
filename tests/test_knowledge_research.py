import pytest

from ctf_copilot.core.knowledge import KnowledgeBase, Lesson
from ctf_copilot.core.permissions import PermissionDenied
from ctf_copilot.llm.tool_router import parse_llm_response
from ctf_copilot.tools import web_research


# ---- knowledge base ----
def test_knowledge_add_and_relevant(tmp_path):
    kb = KnowledgeBase(tmp_path / "k.sqlite")
    kb.add_lesson(Lesson("crypto", "RSA small e", "tiny exponent",
                          "take integer cube root of c", "rsa math"))
    kb.add_lesson(Lesson("web", "SQLi login", "auth bypass",
                          "use ' OR 1=1 -- ", "sqli"))
    assert kb.count() == 2

    hits = kb.relevant("crypto", "rsa cube root exponent", limit=5)
    assert hits and hits[0]["title"] == "RSA small e"

    # category boost: crypto lesson ranks above an unrelated query in-category
    hits2 = kb.relevant("crypto", "completely unrelated words", limit=5)
    assert any(h["category"] == "crypto" for h in hits2)


def test_knowledge_multi_instance_same_file(tmp_path):
    p = tmp_path / "shared.sqlite"
    a = KnowledgeBase(p)
    b = KnowledgeBase(p)  # second "instance"
    a.add_lesson(Lesson("pwn", "ret2libc", "no canary", "leak libc, ret", ""))
    b.add_lesson(Lesson("pwn", "fmtstr", "%n write", "GOT overwrite", ""))
    assert b.count() == 2 and a.count() == 2
    a.close()
    b.close()


# ---- internet research SSRF guards (no network needed) ----
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "http://localhost/secret",
        "http://127.0.0.1:8000/",
        "http://10.0.0.5/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.1/",
    ],
)
def test_research_blocks_unsafe_hosts(url):
    with pytest.raises(PermissionDenied):
        web_research._assert_safe_host(url)


def test_research_html_to_text_strips_markup():
    txt = web_research.html_to_text(
        "<html><script>evil()</script><p>Hello <b>world</b></p></html>"
    )
    assert "Hello world" in txt
    assert "evil" not in txt


# ---- action validation ----
def test_tool_router_accepts_web_actions():
    r = parse_llm_response(
        '{"action":{"type":"web.search","name":"","args":{"query":"rsa ctf"}}}'
    )
    assert r.action.type == "web.search"
    r2 = parse_llm_response(
        '{"action":{"type":"web.fetch","name":"",'
        '"args":{"url":"https://example.com"}}}'
    )
    assert r2.action.type == "web.fetch"
