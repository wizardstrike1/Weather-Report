from pathlib import Path

from ctf_copilot.core.project import (
    STATUS_AWAITING,
    STATUS_INCOMPLETE,
    STATUS_SOLVED,
    Project,
    read_status,
    slugify,
)
from ctf_copilot.writeup import generator


def test_slugify():
    assert slugify("Web 101: SQLi!") == "web-101-sqli"
    assert slugify("   ") == "challenge"


def test_project_lifecycle_and_writeup(tmp_path):
    proj = Project.create(tmp_path, "Test Chal", "web", "https://ctf.example/x")
    for sub in ("downloads", "artifacts", "screenshots", "logs", "tool_outputs"):
        assert (proj.root / sub).is_dir()

    proj.state.add_fact("found login form")
    proj.state.add_action("tool.run", "strings -> nothing", True)
    proj.state.add_flag_candidate("flag{written_up}", "file", 0.9)
    proj.state.mark_flag_submitted("flag{written_up}")
    proj.set_solved(True)

    paths = generator.generate(proj)
    assert paths["markdown"].exists() and paths["html"].exists()
    md = paths["markdown"].read_text("utf-8")
    assert "flag{written_up}" in md
    assert "Test Chal" in md

    # reopen round-trips
    proj.close()
    reopened = Project.open(proj.root)
    assert reopened.solved
    assert "flag{written_up}" in [
        r["value"] for r in reopened.state.flag_candidates()
    ]


def test_metadata_edits_survive_reopen(tmp_path):
    proj = Project.create(tmp_path, "Orig")
    proj.update_metadata("Orig", "pwn", "https://ctf.example/p", "HTB{...}")
    proj.close()
    re = Project.open(proj.root)
    assert re.category == "pwn"
    assert re.url == "https://ctf.example/p"
    assert re.flag_format == "HTB{...}"
    # manifest (not just sqlite) was updated
    import json

    man = json.loads((re.root / "project.json").read_text("utf-8"))
    assert man["category"] == "pwn" and man["url"] == "https://ctf.example/p"


def test_downloads_notes_flags_survive_reopen(tmp_path):
    proj = Project.create(tmp_path, "persist")
    proj.state.add_download("downloads/a.bin", "http://x/a", "deadbeef")
    proj.state.add_note("try xor", "hypothesis")
    proj.state.add_flag_candidate("flag{persist}", "file", 0.8)
    proj.state.add_action("tool.run", "strings -> hit", True)
    proj.close()

    re = Project.open(proj.root)
    assert [r["path"] for r in re.state.downloads()] == ["downloads/a.bin"]
    assert any(n["content"] == "try xor" for n in re.state.notes())
    assert any(
        f["value"] == "flag{persist}" for f in re.state.flag_candidates()
    )
    assert any(
        a["kind"] == "tool.run" for a in re.state.recent_actions()
    )


def test_project_status_lifecycle(tmp_path):
    proj = Project.create(tmp_path, "statuses")
    assert proj.status == STATUS_INCOMPLETE
    assert read_status(proj.root) == STATUS_INCOMPLETE

    proj.set_status(STATUS_AWAITING)
    assert read_status(proj.root) == STATUS_AWAITING
    assert not proj.solved

    proj.set_solved(True)
    assert proj.status == STATUS_SOLVED
    assert proj.solved
    proj.close()
    assert read_status(proj.root) == STATUS_SOLVED
    assert Project.open(proj.root).solved

    # missing/corrupt db -> safe default
    assert read_status(tmp_path / "nonexistent") == STATUS_INCOMPLETE


def test_snapshot_clips_values_and_uses_basenames(tmp_path):
    proj = Project.create(tmp_path, "clip")
    proj.state.add_fact("F" * 5000)  # huge fact
    proj.state.add_download(
        str(tmp_path / "clip" / "downloads" / "payload.bin"), "", "deadbeef"
    )
    snap = proj.state.snapshot()
    assert len(snap["facts"][0]) <= 401  # 400 + ellipsis
    assert snap["downloads"] == ["payload.bin"]  # basename only, not full path


def test_state_snapshot_is_bounded(tmp_path):
    proj = Project.create(tmp_path, "snap")
    for i in range(50):
        proj.state.add_fact(f"fact {i}")
    snap = proj.state.snapshot(max_items=8)
    assert len(snap["facts"]) == 8
