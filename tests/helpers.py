"""Synthetic fixtures shared by the tests. No real research data is ever used."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np


def wall_signal(duration_s: float, rate: int, seed: int = 1) -> np.ndarray:
    """Speech-like synthetic 'real-world' sound: band-limited noise with random bursts.

    Non-periodic (so the correlation peak is unique) and deterministic per seed.
    """
    rng = np.random.default_rng(seed)
    n = int(duration_s * rate)
    noise = rng.standard_normal(n)
    # crude low-pass by moving average so the spectrum is not pure white
    k = max(1, rate // 4000)
    if k > 1:
        noise = np.convolve(noise, np.ones(k) / k, mode="same")
    # slowly varying random envelope (bursts / silences)
    env_pts = rng.random(int(duration_s * 4) + 2) ** 2
    env = np.interp(np.arange(n) / rate * 4, np.arange(env_pts.size), env_pts)
    x = noise * (0.05 + env)
    return (x / np.max(np.abs(x))).astype(np.float32)


def recording(wall: np.ndarray, rate: int, start_s: float, length_s: float) -> np.ndarray:
    """What a camera that started at wall time `start_s` records."""
    a = int(round(start_s * rate))
    return wall[a:a + int(round(length_s * rate))]


def write_wav(path: Path, x: np.ndarray, rate: int) -> None:
    pcm = np.clip(x, -1, 1)
    pcm = (pcm * 32000).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def make_video(path: Path, audio: np.ndarray | None, rate: int, duration_s: float,
               size: str = "160x120", fps: int = 10) -> None:
    """Tiny test video (H.264 + optional AAC) whose audio is `audio`.

    The picture is a frame counter (testsrc) so trimming can also be inspected.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}:duration={duration_s}"]
    wav = None
    if audio is not None:
        wav = path.with_suffix(".tmp.wav")
        write_wav(wav, audio, rate)
        cmd += ["-i", str(wav)]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-g", str(fps)]
    if audio is not None:
        cmd += ["-c:a", "aac", "-b:a", "96k", "-shortest"]
    else:
        cmd += ["-an"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True, capture_output=True)
    if wav is not None:
        wav.unlink()
