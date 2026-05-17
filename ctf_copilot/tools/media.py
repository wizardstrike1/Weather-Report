"""Audio/video analysis built-ins.

Pure-Python where possible (numpy + stdlib `wave`) so spectrogram / LSB /
tone-envelope work on Windows with no ffmpeg. External tools
(ffmpeg/multimon-ng/zbarimg/pyzbar) are used when present and degrade
gracefully otherwise. Every function returns a string and never raises — the
solver wraps the result in the prompt-injection guardrail.

Key idea for "comprehension": Claude can't hear audio, so the workflow is
make a spectrogram PNG (or extract frames) -> `vision.look` the image.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import wave
from pathlib import Path

_MAX_SAMPLES = 60 * 44100  # cap analysis to ~60 s of audio


def _read_wav(path: Path):
    """Return (mono_int16_list_as_bytes-free, framerate, nchan) or raise."""
    import numpy as np

    with wave.open(str(path), "rb") as w:
        nch, sw, fr, nfr = (w.getnchannels(), w.getsampwidth(),
                            w.getframerate(), w.getnframes())
        raw = w.readframes(min(nfr, _MAX_SAMPLES))
    # Normalise any sample width to int16 with numpy (no `audioop`, which is
    # removed in Python 3.13).
    if sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.int16)
    elif sw == 1:  # 8-bit WAV is unsigned
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128) * 256
    elif sw == 4:
        a = (np.frombuffer(raw, dtype="<i4") >> 16).astype(np.int16)
    elif sw == 3:  # packed 24-bit little-endian
        b = np.frombuffer(raw, dtype=np.uint8)
        b = b[: (len(b) // 3) * 3].reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v[v >= 1 << 23] -= 1 << 24
        a = (v >> 8).astype(np.int16)
    else:
        raise ValueError(f"unsupported sample width {sw}")
    if nch > 1:
        a = a[: (len(a) // nch) * nch].reshape(-1, nch).mean(
            axis=1).astype(np.int16)
    return a, fr, nch, sw


def _ensure_wav(path: Path, out_dir: Path) -> Path | None:
    """Return a WAV path: the file itself if WAV, else ffmpeg-transcoded."""
    if path.suffix.lower() == ".wav":
        return path
    if shutil.which("ffmpeg") is None:
        return None
    dst = out_dir / (path.stem + ".conv.wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-ac", "1", "-ar", "44100",
             str(dst)],
            capture_output=True, timeout=120, shell=False,
        )
        return dst if dst.exists() else None
    except (OSError, subprocess.SubprocessError):
        return None


def audio_summary(path: Path, out_dir: Path) -> str:
    wav = _ensure_wav(path, out_dir)
    if wav is None:
        return (f"{path.name}: not WAV and ffmpeg not installed — install "
                "ffmpeg to analyse compressed audio, or convert to WAV.")
    try:
        a, fr, nch, sw = _read_wav(wav)
    except Exception as e:  # noqa: BLE001
        return f"audio_summary error: {e}"
    dur = len(a) / fr if fr else 0
    import numpy as np

    return (f"audio {path.name}: {fr} Hz, {nch}ch, {sw*8}-bit, "
            f"~{dur:.2f}s, {len(a)} mono samples, "
            f"peak={int(np.abs(a).max()) if len(a) else 0}. "
            f"Next: tool.run spectrogram then vision.look the PNG; or "
            f"tool.run lsb_wav / tones.")


def spectrogram(path: Path, out_dir: Path) -> str:
    """numpy-only STFT -> grayscale PNG. Flags are very often *drawn* here."""
    wav = _ensure_wav(path, out_dir)
    if wav is None:
        return "spectrogram: need WAV or ffmpeg."
    try:
        import numpy as np
        from PIL import Image

        a, fr, _nch, _sw = _read_wav(wav)
        if len(a) < 256:
            return "spectrogram: audio too short."
        sig = a.astype(np.float32)
        nfft, hop = 1024, 256
        win = np.hanning(nfft).astype(np.float32)
        ncols = 1 + (len(sig) - nfft) // hop
        ncols = min(ncols, 4000)
        spec = np.empty((nfft // 2, ncols), dtype=np.float32)
        for i in range(ncols):
            seg = sig[i * hop: i * hop + nfft] * win
            mag = np.abs(np.fft.rfft(seg))[: nfft // 2]
            spec[:, i] = mag
        spec = 20 * np.log10(spec + 1e-6)
        spec -= spec.min()
        if spec.max() > 0:
            spec = spec / spec.max() * 255.0
        img = np.flipud(spec).astype(np.uint8)  # low freq at bottom
        out = out_dir / (path.stem + ".spectrogram.png")
        Image.fromarray(img, mode="L").save(out)
        return (f"spectrogram saved: {out.name} ({img.shape[1]}x"
                f"{img.shape[0]}). Use vision.look {{\"file\":"
                f"\"artifacts/{out.name}\"}} to read any hidden text/flag.")
    except Exception as e:  # noqa: BLE001
        return f"spectrogram error: {e}"


def lsb_wav(path: Path, out_dir: Path) -> str:
    wav = _ensure_wav(path, out_dir)
    if wav is None:
        return "lsb_wav: need WAV or ffmpeg."
    try:
        import re

        import numpy as np

        a, _fr, _nch, _sw = _read_wav(wav)
        bits = (a & 1).astype(np.uint8)
        n = (len(bits) // 8) * 8
        by = np.packbits(bits[:n]).tobytes()
        txt = by.decode("latin-1", "replace")
        flags = re.findall(r"[A-Za-z0-9_]{2,16}\{[^}\r\n]{1,256}\}", txt)
        printable = "".join(c for c in txt[:2000] if 32 <= ord(c) < 127)
        return (f"lsb_wav: flags={flags or 'none'}\n"
                f"first printable LSB bytes: {printable[:600]}")
    except Exception as e:  # noqa: BLE001
        return f"lsb_wav error: {e}"


def tones(path: Path, out_dir: Path) -> str:
    """multimon-ng (DTMF/Morse/AFSK) if available, else a numpy amplitude
    on/off envelope to help the model decode Morse manually."""
    wav = _ensure_wav(path, out_dir)
    if wav is None:
        return "tones: need WAV or ffmpeg."
    if shutil.which("multimon-ng"):
        try:
            raw = out_dir / (path.stem + ".22k.raw")
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav), "-ac", "1", "-ar", "22050",
                 "-f", "s16le", str(raw)],
                capture_output=True, timeout=120, shell=False,
            )
            r = subprocess.run(
                ["multimon-ng", "-a", "DTMF", "-a", "MORSE_CW",
                 "-a", "AFSK1200", "-t", "raw", str(raw)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=120, shell=False,
            )
            return "multimon-ng:\n" + (r.stdout or r.stderr)[:3000]
        except (OSError, subprocess.SubprocessError) as e:
            return f"tones (multimon-ng) error: {e}"
    try:
        import numpy as np

        a, fr, _nch, _sw = _read_wav(wav)
        env = np.abs(a.astype(np.float32))
        win = max(1, fr // 100)
        env = np.convolve(env, np.ones(win) / win, "same")
        on = env > (env.max() * 0.25)
        # run-length of on/off in ms
        runs, cur, cnt = [], on[0], 0
        for v in on:
            if v == cur:
                cnt += 1
            else:
                runs.append((bool(cur), round(cnt * 1000 / fr)))
                cur, cnt = v, 1
        runs.append((bool(cur), round(cnt * 1000 / fr)))
        return ("multimon-ng not installed. Amplitude on/off durations (ms) "
                "— infer Morse from short/long ON vs gaps:\n"
                + str(runs[:120]))
    except Exception as e:  # noqa: BLE001
        return f"tones error: {e}"


def qr_decode(path: Path) -> str:
    try:
        from PIL import Image

        try:
            from pyzbar.pyzbar import decode as zdecode

            res = zdecode(Image.open(path))
            if res:
                return "QR/barcode: " + " | ".join(
                    d.data.decode("utf-8", "replace") for d in res
                )
            return "qr_decode: no codes found (pyzbar)."
        except ImportError:
            if shutil.which("zbarimg"):
                r = subprocess.run(["zbarimg", "-q", str(path)],
                                   capture_output=True, text=True,
                                   timeout=30, shell=False)
                return "zbarimg: " + (r.stdout.strip() or "no codes")
            return ("qr_decode: install pyzbar (pip) or zbar (zbarimg) to "
                    "decode QR/barcodes; otherwise vision.look the image.")
    except Exception as e:  # noqa: BLE001
        return f"qr_decode error: {e}"


def video_frames(path: Path, out_dir: Path, n: int = 12) -> str:
    if shutil.which("ffmpeg") is None:
        return "video_frames: ffmpeg not installed."
    fdir = out_dir / (path.stem + "_frames")
    fdir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-vf",
             f"thumbnail,scale=640:-1", "-frames:v", str(n),
             str(fdir / "f%02d.png")],
            capture_output=True, timeout=180, shell=False,
        )
        frames = sorted(fdir.glob("*.png"))
        qr = [qr_decode(f) for f in frames]
        qr_hits = [q for q in qr if "no codes" not in q and "error" not in q
                   and "install" not in q]
        return (f"extracted {len(frames)} frame(s) to "
                f"artifacts/{fdir.name}/. QR hits: {qr_hits or 'none'}. "
                f"vision.look individual frames to read on-screen text.")
    except (OSError, subprocess.SubprocessError) as e:
        return f"video_frames error: {e}"


def transcribe(path: Path, out_dir: Path, max_tools: bool) -> str:
    if not max_tools:
        return ("transcribe is gated behind Maximum-tools mode (Whisper is "
                "heavy). Enable it in Settings and `pip install "
                "openai-whisper`.")
    try:
        import whisper  # type: ignore

        wav = _ensure_wav(path, out_dir) or path
        model = whisper.load_model("base")
        text = model.transcribe(str(wav)).get("text", "").strip()
        return f"transcript: {text[:3000]}"
    except ImportError:
        return "transcribe: `pip install openai-whisper` (Maximum-tools)."
    except Exception as e:  # noqa: BLE001
        return f"transcribe error: {e}"
