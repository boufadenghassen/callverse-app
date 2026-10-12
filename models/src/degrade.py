"""Realistic audio degradations for training and testing the emotion model on call-center-like audio.

Real telephone codecs go through ffmpeg (must be on PATH): AMR-NB and GSM (mobile networks), G.711 mu-law (landlines),
Opus at a low bitrate (VoIP / WebRTC). (AMR-WB is left out: it did not round-trip cleanly here, and it is rare on call lines.) Noise and room effects are synthesised, so no extra data has to be downloaded:
babble is built from other speakers in the pool, hum is mains hum, pink/brown noise is coloured noise, reverb is a
synthetic exponential-decay room. All functions take and return float32 mono arrays at 16 kHz.

    python models/src/degrade.py          # self-test: each codec on one clip
"""
import subprocess
import time

import numpy as np
from scipy.signal import fftconvolve

SR = 16000
CODECS = {   # name: (ffmpeg encode arguments, container, sample rate the codec runs at)
    "amr_nb": (["-c:a", "libopencore_amrnb", "-b:a", "7.4k"], "amr", 8000),
    "gsm": (["-c:a", "libgsm"], "gsm", 8000),
    "mulaw": (["-c:a", "pcm_mulaw"], "wav", 8000),
    "opus": (["-c:a", "libopus", "-b:a", "10k", "-application", "voip"], "ogg", 16000),
}


def _pcm16(w: np.ndarray) -> bytes:
    return (np.clip(w, -1, 1) * 32767).astype("<i2").tobytes()


def codec_roundtrip(w: np.ndarray, codec: str) -> np.ndarray:
    """Encode with a real codec and decode again, like a call that went through that network."""
    args, container, rate = CODECS[codec]
    enc = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "pipe:0", "-ar", str(rate), "-ac", "1",
                          *args, "-f", container, "pipe:1"], input=_pcm16(w), capture_output=True, check=True).stdout
    dec = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", container, "-i", "pipe:0", "-ar", str(SR), "-ac", "1", "-f", "s16le", "pipe:1"],
                         input=enc, capture_output=True, check=True).stdout
    out = np.frombuffer(dec, dtype="<i2").astype(np.float32) / 32767
    return np.pad(out, (0, max(0, len(w) - len(out))))[: len(w)]          # codecs add a little delay or padding: keep the length


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x))) + 1e-8)


def add_at_snr(w: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    return w + noise * (rms(w) / rms(noise)) / 10 ** (snr_db / 20)


def babble(pool, n: int, rng: np.random.Generator, speakers=(3, 6)) -> np.ndarray:
    """Several other people talking at once: random crops of random pool clips, summed."""
    mix = np.zeros(n, np.float32)
    for _ in range(int(rng.integers(speakers[0], speakers[1] + 1))):
        w = pool[int(rng.integers(len(pool)))].astype(np.float32)
        if len(w) < n:
            w = np.tile(w, n // len(w) + 1)
        s = int(rng.integers(0, len(w) - n + 1))
        seg = w[s:s + n]
        mix += seg / rms(seg) * 10 ** (rng.uniform(-6, 0) / 20)
    return mix


def hum(n: int, freq: float, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / SR
    return sum(rng.uniform(0.3, 1.0) / h * np.sin(2 * np.pi * freq * h * t + rng.uniform(0, 6.28)) for h in range(1, 5)).astype(np.float32)


def coloured(n: int, kind: str, rng: np.random.Generator) -> np.ndarray:
    """Pink (1/f) or brown (1/f^2) noise by shaping the spectrum of white noise."""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.maximum(np.arange(len(spec)), 1).astype(np.float64)
    spec /= f ** ({"pink": 0.5, "brown": 1.0}[kind])
    return np.fft.irfft(spec, n).astype(np.float32)


def reverb(w: np.ndarray, rt60: float, rng: np.random.Generator) -> np.ndarray:
    """A synthetic small room: noise that decays by 60 dB in rt60 seconds, convolved with the voice."""
    t = np.arange(int(rt60 * SR)) / SR
    ir = rng.standard_normal(len(t)) * np.exp(-6.9 * t / rt60)
    ir[0] = 3.0
    out = fftconvolve(w, ir / np.sqrt((ir ** 2).sum()))[: len(w)].astype(np.float32)
    return out / rms(out) * rms(w)


def packet_loss(w: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A few short dropouts, 20 to 60 ms, as on a bad VoIP link."""
    w = w.copy()
    for _ in range(int(rng.integers(2, 5))):
        n = int(rng.integers(int(0.02 * SR), int(0.06 * SR) + 1))
        s = int(rng.integers(0, max(1, len(w) - n)))
        w[s:s + n] = 0
    return w


def finish(w: np.ndarray) -> np.ndarray:
    return (w / max(float(np.abs(w).max()), 1e-6) * 0.95).astype(np.float32)


if __name__ == "__main__":
    t = np.arange(SR * 2) / SR
    voice = (0.6 * np.sin(2 * np.pi * 220 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t)) + 0.2 * np.sin(2 * np.pi * 1800 * t)).astype(np.float32)
    for name in CODECS:
        t0 = time.time()
        out = codec_roundtrip(voice, name)
        print(f"{name:7s} ok, {len(out)} samples, correlation with the original {np.corrcoef(voice, out)[0, 1]:.2f}, {(time.time() - t0) * 1000:.0f} ms")
