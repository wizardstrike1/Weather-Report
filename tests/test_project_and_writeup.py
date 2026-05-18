from pathlib import Path

from ctf_copilot.core.project import (
    STATUS_AWAITING,
    STATUS_INCOMPLETE,
    STATUS_SOLVED,
    Project,
    delete_project,
    move_project,
    read_card,
    read_status,
    rename_group,
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


def test_move_rename_delete_project(tmp_path):
    a = Project.create(tmp_path, "Chal A", category="web", competition="EventX")
    b = Project.create(tmp_path, "Chal B", competition="EventX")
    a.close()
    b.close()
    assert read_card(a.root)["competition"] == "EventX"

    # move A into a different group
    new_root = move_project(a.root, tmp_path, "EventY")
    assert new_root.exists() and not a.root.exists()
    card = read_card(new_root)
    assert card["competition"] == "EventY" and card["name"] == "Chal A"
    reopened = Project.open(new_root)
    assert reopened.competition == "EventY"
    assert reopened.state.get_meta("competition") == "EventY"
    reopened.close()

    # rename the remaining group (B is still in EventX)
    n = rename_group(tmp_path, "EventX", "Finals")
    assert n == 1
    bcards = [
        read_card(p.parent) for p in tmp_path.rglob("project.json")
    ]
    assert any(c["competition"] == "Finals" for c in bcards)
    assert not any(c["competition"] == "EventX" for c in bcards)

    # delete A
    delete_project(new_root)
    assert not new_root.exists()


def test_move_project_dedupes_name_clash(tmp_path):
    p1 = Project.create(tmp_path, "Dup", competition="G1")
    p2 = Project.create(tmp_path, "Dup", competition="G2")
    p1.close()
    p2.close()
    moved = move_project(p2.root, tmp_path, "G1")
    # both now under G1 group, different folder names
    assert moved.exists() and p1.root.exists()
    assert moved.name != p1.root.name


def test_reset_clears_agent_state_keeps_identity(tmp_path):
    p = Project.create(tmp_path, "ResetMe", category="web",
                       url="https://ctf.x/c", competition="EventR")
    st = p.state
    st.set_meta("user_context", "given hint context")
    st.add_fact("agent fact")
    st.add_action("tool.run", "ran strings", True)
    st.add_tool_output("strings", "argv", "out", "log")
    st.add_flag_candidate("flag{wrong}", "agent", 0.4)
    st.add_note("a hypothesis", "hypothesis")
    st.add_note("user hint kept", "hint")
    st.add_download("downloads/chal.bin", "import:x", "deadbeef")
    (p.artifacts_dir / "solve.py").write_text("print(1)", "utf-8")
    (p.screenshots_dir / "s.png").write_bytes(b"x")
    p.set_solved(True)
    st.set_meta("tokens_spent", "12345")

    p.reset()

    # identity preserved
    assert p.state.get_meta("name") == "ResetMe"
    assert p.state.get_meta("url") == "https://ctf.x/c"
    assert p.state.get_meta("competition") == "EventR"
    assert p.state.get_meta("user_context") == "given hint context"
    assert read_card(p.root)["category"] == "web"  # manifest intact
    # agent state cleared
    assert p.state.facts() == []
    assert p.state.flag_candidates() == []
    assert list(p.state.recent_actions()) == []
    assert p.state.get_meta("status") == "incomplete"
    assert p.state.get_meta("tokens_spent") == "0"
    # hints + downloads kept; hypotheses/notes gone
    notes = p.state.notes()
    assert any(n["kind"] == "hint" for n in notes)
    assert not any(n["kind"] == "hypothesis" for n in notes)
    assert [r["path"] for r in p.state.downloads()] == ["downloads/chal.bin"]
    # generated dirs emptied but still exist
    assert p.artifacts_dir.is_dir()
    assert list(p.artifacts_dir.iterdir()) == []
    assert list(p.screenshots_dir.iterdir()) == []


def test_state_snapshot_is_bounded(tmp_path):
    proj = Project.create(tmp_path, "snap")
    for i in range(50):
        proj.state.add_fact(f"fact {i}")
    snap = proj.state.snapshot(max_items=8)
    assert len(snap["facts"]) == 8
