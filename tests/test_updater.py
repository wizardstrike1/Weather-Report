"""Updater logic (no network — we don't call git fetch here)."""
from ctf_copilot.core import updater
from ctf_copilot.core.updater import UpdateStatus


def test_update_status_available_rules():
    assert UpdateStatus(supported=True, behind=3).available is True
    assert UpdateStatus(supported=True, behind=0).available is False
    assert UpdateStatus(supported=False, behind=9).available is False
    assert UpdateStatus(supported=True, behind=5, error="boom").available is False


def test_is_git_checkout_returns_bool():
    assert isinstance(updater.is_git_checkout(), bool)


def test_head_commit_is_str_and_status_has_head():
    assert isinstance(updater.head_commit(), str)
    assert UpdateStatus().head == ""
    # a stale process: behind==0 (nothing to pull) but head != boot commit
    st = UpdateStatus(supported=True, behind=0, head="abc1234")
    assert st.available is False  # 'available' is still pull-only
    assert st.head == "abc1234"


def test_apply_update_guard_when_not_checkout(monkeypatch):
    monkeypatch.setattr(updater, "is_git_checkout", lambda: False)
    ok, msg = updater.apply_update("main")
    assert ok is False and "manually" in msg.lower()
