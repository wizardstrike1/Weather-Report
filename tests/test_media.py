"""Audio/video built-ins (pure-Python: numpy + stdlib wave; no ffmpeg/net)."""
import wave

import numpy as np
import pytest

from ctf_copilot.llm.tool_router import parse_llm_response
from ctf_copilot.tools import media


def _write_wav(path, samples, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.astype("<i2").tobytes())


def test_audio_summary_parses_wav(tmp_path):
    f = tmp_path / "a.wav"
    _write_wav(f, (np.sin(np.arange(8000) * 0.1) * 1000).astype("int16"))
    out = media.audio_summary(f, tmp_path)
    assert "8000 Hz" in out and "1ch" in out


def test_spectrogram_writes_png(tmp_path):
    f = tmp_path / "s.wav"
    t = np.arange(16000)
    sig = (np.sin(2 * np.pi * 440 * t / 8000) * 8000).astype("int16")
    _write_wav(f, sig)
    out = media.spectrogram(f, tmp_path)
    assert "spectrogram saved" in out
    png = tmp_path / "s.spectrogram.png"
    assert png.exists() and png.stat().st_size > 100


def test_lsb_wav_recovers_planted_flag(tmp_path):
    flag = b"flag{lsb_audio_works}"
    bits = np.unpackbits(np.frombuffer(flag, dtype=np.uint8))
    # carrier longer than payload; set LSBs to the flag bits, rest random
    rng = np.random.default_rng(0)
    samp = (rng.integers(-5000, 5000, size=4000)).astype("int16")
    samp[: len(bits)] = (samp[: len(bits)] & ~1) | bits
    f = tmp_path / "l.wav"
    _write_wav(f, samp)
    out = media.lsb_wav(f, tmp_path)
    assert "flag{lsb_audio_works}" in out


def test_qr_decode_is_graceful_without_libs(tmp_path):
    from PIL import Image

    p = tmp_path / "img.png"
    Image.new("RGB", (32, 32), "white").save(p)
    out = media.qr_decode(p)
    assert isinstance(out, str) and "error" not in out.lower()


def test_tones_envelope_fallback(tmp_path):
    f = tmp_path / "t.wav"
    # 100ms tone, 100ms silence, repeated
    rate = 8000
    seg = np.concatenate([
        (np.sin(2 * np.pi * 600 * np.arange(rate // 10) / rate) * 9000),
        np.zeros(rate // 10),
    ]).astype("int16")
    _write_wav(f, np.tile(seg, 5))
    out = media.tones(f, tmp_path)
    assert "durations" in out or "multimon" in out


def test_tool_router_accepts_vision_look():
    r = parse_llm_response(
        '{"action":{"type":"vision.look","name":"",'
        '"args":{"file":"artifacts/x.spectrogram.png"}}}'
    )
    assert r.action.type == "vision.look"
    assert r.action.args["file"].endswith(".png")


def test_transcribe_gated_off_message(tmp_path):
    f = tmp_path / "v.wav"
    _write_wav(f, np.zeros(800).astype("int16"))
    assert "Maximum-tools" in media.transcribe(f, tmp_path, max_tools=False)
