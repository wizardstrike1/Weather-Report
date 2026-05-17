import pytest

from ctf_copilot.core.permissions import PermissionDenied, Permissions


def test_path_inside_workspace_ok(tmp_path):
    p = Permissions(tmp_path, [])
    (tmp_path / "downloads").mkdir()
    f = tmp_path / "downloads" / "a.bin"
    f.write_bytes(b"x")
    assert p.resolve_in_workspace("downloads/a.bin", must_exist=True) == f.resolve()


def test_path_escape_blocked(tmp_path):
    p = Permissions(tmp_path, [])
    with pytest.raises(PermissionDenied):
        p.resolve_in_workspace("../../etc/passwd")
    with pytest.raises(PermissionDenied):
        p.resolve_in_workspace("downloads/../../secret")


def test_allowed_domain_validation(tmp_path):
    p = Permissions(tmp_path, ["ctf.example", "10.0.0.5"])
    assert p.check_url("https://ctf.example/chal")
    assert p.check_url("http://sub.ctf.example/x")
    with pytest.raises(PermissionDenied):
        p.check_url("https://evil.com/x")
    with pytest.raises(PermissionDenied):
        p.check_url("https://notctf.example.attacker.com")


def test_empty_allowlist_denies_all(tmp_path):
    p = Permissions(tmp_path, [])
    with pytest.raises(PermissionDenied):
        p.check_url("https://anything.com")


def test_allow_all_domains_opt_in(tmp_path):
    # default: deny-all
    assert Permissions(tmp_path, []).allow_all is False
    # opt-in: every host passes, allowlist irrelevant
    p = Permissions(tmp_path, [], allow_all=True)
    assert p.check_url("https://anything.example/x")
    assert p.check_url("http://10.9.8.7:1337/pwn")
    assert p.check_network_target("evil.test:4444")
