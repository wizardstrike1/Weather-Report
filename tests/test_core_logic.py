import pytest

from ctf_copilot.core.permissions import PermissionDenied, Permissions
from ctf_copilot.llm.token_budget import TokenBudget, truncate_to_tokens
from ctf_copilot.llm.tool_router import parse_llm_response
from ctf_copilot.llm.claude_client import ClaudeClient
from ctf_copilot.tools import crypto_tools
from ctf_copilot.tools.registry import BY_NAME, ToolRegistry
from ctf_copilot.tools.sandbox import build_command


# ---- registry ----
def test_registry_specs_well_formed():
    for name, spec in BY_NAME.items():
        assert spec.name == name
        assert spec.template and spec.template[0] == spec.binary
        if spec.requires_target:
            assert any("{target}" in t for t in spec.template)


def test_registry_availability_shape():
    rows = ToolRegistry().availability()
    assert all({"name", "available", "category"} <= r.keys() for r in rows)


# ---- sandbox ----
def test_sandbox_blocks_path_escape(tmp_path):
    perms = Permissions(tmp_path, ["x.com"])
    spec = BY_NAME["strings"]
    with pytest.raises(PermissionDenied):
        build_command(spec, "strings", {"file": "../../etc/passwd"}, perms)


def test_sandbox_blocks_unlisted_target(tmp_path):
    perms = Permissions(tmp_path, ["ctf.example"])
    with pytest.raises(PermissionDenied):
        build_command(BY_NAME["curl"], "curl", {"target": "http://evil.com"}, perms)


# ---- token budget ----
def test_truncate():
    s = "a" * 10_000
    out = truncate_to_tokens(s, 100)
    assert len(out) < len(s) and "elided" in out


def test_fit_prompt_uses_prompt_cap_not_completion_size():
    big = "x" * 80_000  # ~20k tokens
    # tiny completion size (per_step_limit) must NOT shrink the prompt;
    # a generous prompt cap (>= 20k tokens) leaves it intact.
    b = TokenBudget(10_000_000, per_step_limit=512, prompt_token_cap=30_000)
    assert b.fit_prompt(big) == big
    # the prompt cap (not per_step_limit) is what truncates
    b2 = TokenBudget(10_000_000, per_step_limit=512, prompt_token_cap=2_000)
    out = b2.fit_prompt(big)
    assert "elided" in out
    assert 512 * 4 < len(out) < len(big)  # bounded by 2k tokens, not 512


def test_budget_accounting():
    b = TokenBudget(session_limit=1000, per_step_limit=200)
    assert b.can_spend(500)
    b.record(400, 200)
    assert b.remaining() == 400
    assert not b.can_spend(500)


# ---- tool router ----
def test_build_user_message_is_compact_json():
    import json as _j

    from ctf_copilot.llm.prompt_builder import build_user_message

    msg = build_user_message(
        {"challenge": {"name": "x"}}, {"unchanged": True}, "hist",
        ["file.inspect", "tool.run"], lessons=[{"title": "t"}],
        internet_research=False,
    )
    # exactly one newline (the short preamble); JSON itself has no indentation
    assert msg.count("\n") == 1
    payload = _j.loads(msg.split("\n", 1)[1])
    assert payload["available_tools"] == "file.inspect,tool.run"  # comma str
    assert ", " not in msg and ": " not in msg  # minified separators


def test_parse_valid_action():
    raw = """```json
    {"thought_summary":"x","hypothesis":"y",
     "action":{"type":"tool.run","name":"strings","args":{"file":"a.bin"}},
     "risk":"low","needs_user_approval":false,"notes_to_save":[]}
    ```"""
    r = parse_llm_response(raw)
    assert r.action.type == "tool.run"
    assert r.action.name == "strings"


def test_parse_accepts_browser_upload():
    r = parse_llm_response(
        '{"thought_summary":"","hypothesis":"",'
        '"action":{"type":"browser.upload","name":"",'
        '"args":{"selector":"input[type=file]","files":"artifacts/shell.php"}},'
        '"risk":"medium","needs_user_approval":true,"notes_to_save":[]}'
    )
    assert r.action.type == "browser.upload"
    assert r.action.args["files"] == "artifacts/shell.php"


def test_args_coercion_accepts_bool_int_list():
    r = parse_llm_response(
        '{"action":{"type":"file.inspect","name":"",'
        '"args":{"file":"downloads/x.py","full":true,"max_bytes":4096,'
        '"opts":["a","b"],"none":null}}}'
    )
    a = r.action.args
    assert a["file"] == "downloads/x.py"
    assert a["full"] == "true"
    assert a["max_bytes"] == "4096"
    assert a["opts"] == '["a","b"]'
    assert a["none"] == ""


def test_parse_rejects_unknown_action_type():
    with pytest.raises(ValueError):
        parse_llm_response('{"action":{"type":"os.system","name":"rm"}}')


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_llm_response("not json at all")


# ---- LLM backend fallback ----
def test_backend_manual_when_no_key_and_no_cli():
    c = ClaudeClient(None, "m", 1024, cli_command="definitely-not-a-real-binary-xyz")
    assert c.backend == "manual"
    assert c.manual_mode is True


def test_backend_picks_cli_when_present():
    # 'python' is guaranteed on PATH in CI; stands in for the claude binary
    c = ClaudeClient(None, "m", 1024, cli_command="python")
    assert c.backend == "cli"
    assert c.manual_mode is False


def test_manual_response_is_valid_action_json():
    c = ClaudeClient(None, "m", 1024, cli_command="definitely-not-a-real-binary-xyz")
    res = c.complete("hello", TokenBudget(1000, 500))
    parsed = parse_llm_response(res.raw_text)
    assert parsed.action.type == "ask_user"


# ---- crypto helpers ----
def test_base64_decode():
    out = crypto_tools.try_base_decodings("ZmxhZ3t0ZXN0fQ==")
    assert out.get("base64") == "flag{test}"


def test_single_byte_xor_recovers():
    plain = b"flag{xor_me_please}"
    cipher = bytes(b ^ 0x42 for b in plain)
    results = crypto_tools.single_byte_xor(cipher)
    assert any("flag{xor_me_please}" in dec for _, dec, _ in results)


def test_hash_identification():
    assert "MD5" in crypto_tools.identify_hash("d41d8cd98f00b204e9800998ecf8427e")
    assert "SHA-256" in crypto_tools.identify_hash("a" * 64)
