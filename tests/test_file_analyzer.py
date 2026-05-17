import io
import zipfile

from ctf_copilot.tools import file_analyzer


def test_identify_and_flag(tmp_path):
    f = tmp_path / "note.txt"
    f.write_bytes(b"nothing here ... flag{unit_test_flag} ... end")
    res = file_analyzer.analyze(f)
    assert "text" in res.file_type
    assert "flag{unit_test_flag}" in res.flag_candidates
    assert res.sha256


def test_entropy_high_for_random(tmp_path):
    import os

    f = tmp_path / "rand.bin"
    f.write_bytes(os.urandom(4096))
    res = file_analyzer.analyze(f)
    assert res.entropy > 7.0


def test_png_magic(tmp_path):
    f = tmp_path / "img"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    assert "PNG" in file_analyzer.analyze(f).file_type


def test_zip_extraction_is_sandboxed(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../evil.txt", "flag{zip_slip_blocked}")
    zp = tmp_path / "a.zip"
    zp.write_bytes(buf.getvalue())
    out = tmp_path / "out"
    res = file_analyzer.analyze(zp, extract_to=out)
    # path was flattened to basename -> stays inside out/
    for ex in res.extracted:
        assert str(out) in ex
