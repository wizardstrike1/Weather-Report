"""The agent must be able to run code itself (the autonomy fix): python tool
+ stdin + script_args, all shell-free and workspace-sandboxed."""
import sys

from ctf_copilot.core.permissions import Permissions
from ctf_copilot.llm.tool_router import parse_llm_response
from ctf_copilot.tools.registry import BY_NAME, ToolRegistry
from ctf_copilot.tools.runner import ToolRunner


def test_python_tool_registered():
    assert "python" in BY_NAME
    assert BY_NAME["python"].template[0] == "python"
    assert not BY_NAME["python"].optional


def test_runner_runs_python_with_stdin_and_argv(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    out = ws / "tool_outputs"
    out.mkdir()
    (ws / "solve.py").write_text(
        "import sys\n"
        "data = sys.stdin.read().strip()\n"
        "print('STDIN=' + data)\n"
        "print('ARGV=' + ','.join(sys.argv[1:]))\n",
        "utf-8",
    )
    perms = Permissions(ws, [])
    runner = ToolRunner(ToolRegistry(), perms, out, min_interval_s=0.0)

    # use whatever python binary is running the tests
    reg = ToolRegistry({"python": sys.executable})
    runner = ToolRunner(reg, perms, out, min_interval_s=0.0)

    res = runner.run(
        "python",
        {"file": "solve.py", "stdin": "ciphertext", "script_args": '["A","B"]'},
        approved=True,
    )
    assert res.returncode == 0, res.summary
    assert "STDIN=ciphertext" in res.summary
    assert "ARGV=A,B" in res.summary
    # full log persisted locally
    assert res.log_path.exists()


def test_runner_blocks_script_outside_workspace(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "tool_outputs").mkdir()
    perms = Permissions(ws, [])
    reg = ToolRegistry({"python": sys.executable})
    runner = ToolRunner(reg, perms, ws / "tool_outputs", min_interval_s=0.0)
    import pytest

    from ctf_copilot.core.permissions import PermissionDenied

    with pytest.raises(PermissionDenied):
        runner.run("python", {"file": "../evil.py"}, approved=True)


def test_tool_router_accepts_file_write():
    r = parse_llm_response(
        '{"action":{"type":"file.write","name":"",'
        '"args":{"file":"artifacts/solve.py","content":"print(1)"}}}'
    )
    assert r.action.type == "file.write"
    assert r.action.args["content"] == "print(1)"
