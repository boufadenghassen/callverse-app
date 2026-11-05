"""Quality review of a call RECORDING.

Call centers record the two sides on two channels: the advisor on the left, the customer on the right. That is what this agent expects, because
it makes the speaker of every sentence certain (no guessing who is talking). Each channel goes through speech to text with times (Whisper),
the customer's sentences go through the emotion model (models/src/serve.py, port 8001) to get the mood, and the transcript is scored by
quality.review(). Without the emotion service the mood falls back to a word list and the review says so (`moodSource`: "text").

`sample_call()` builds a two-channel example with the neural voices, so the feature can be tried without a recording.
"""
import io
import os
from functools import lru_cache
from pathlib import Path

import httpx
import librosa
import numpy as np
import soundfile as sf

from . import engine as quality
import stt
import voice

EMOTION_URL = os.environ.get("EMOTION_URL", "http://localhost:8001")
MAX_SECONDS = 300
MERGE_GAP = 1.5          # sentences of the same speaker closer than this (seconds) are one turn


class NeedsTwoChannels(ValueError):
    pass


def _channels(wav: bytes) -> tuple[np.ndarray, np.ndarray, int]:
    try:
        y, sr = sf.read(io.BytesIO(wav), dtype="float32", always_2d=True)
    except Exception:
        raise stt.BadAudio("Could not read this recording.")
    if y.shape[1] < 2:
        raise NeedsTwoChannels("A quality review needs a two-channel recording: the advisor on the left, the customer on the right.")
    y = y[: MAX_SECONDS * sr]
    return y[:, 0], y[:, 1], sr


def _to16k(x: np.ndarray, sr: int) -> np.ndarray:
    return librosa.resample(x, orig_sr=sr, target_sr=stt.SR) if sr != stt.SR else x


def _emotion(clip: np.ndarray) -> dict | None:
    """The emotion model's answer for one customer sentence, or None when the service is not running or the clip is too short."""
    if len(clip) < stt.SR // 2:
        return None
    buf = io.BytesIO()
    sf.write(buf, clip, stt.SR, format="WAV", subtype="PCM_16")
    try:
        r = httpx.post(f"{EMOTION_URL}/emotion/analyze", content=buf.getvalue(), timeout=60)
        return r.json() if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


def _turns(adv: list[dict], cus: list[dict], right: np.ndarray) -> list[dict]:
    merged = []
    for speaker, segs in (("advisor", adv), ("customer", cus)):
        cur = None
        for s in segs:
            if cur and s["start"] - cur["end"] <= MERGE_GAP:
                cur["text"] += " " + s["text"]
                cur["end"] = s["end"]
            else:
                cur = dict(speaker=speaker, text=s["text"], start=s["start"], end=s["end"])
                merged.append(cur)
    merged.sort(key=lambda t: t["start"])
    for t in merged:
        if t["speaker"] == "customer":
            e = _emotion(right[int(t["start"] * stt.SR): int(t["end"] * stt.SR)])
            if e:
                t["mood"], t["emotion"] = e["mood"], e["emotion"]
    return merged


def transcript(wav: bytes) -> list[dict]:
    left, right, sr = _channels(wav)
    left, right = _to16k(left, sr), _to16k(right, sr)
    turns = _turns(stt.transcribe_segments(left), stt.transcribe_segments(right), right)
    if not turns:
        raise stt.BadAudio("I could not hear any speech in this recording.")
    return turns


# ---- a two-channel example call, spoken by the neural voices --------------------------------------------
SAMPLE_SCRIPT = [   # a call with problems on purpose: no greeting, asked to repeat, a promise before the policy check, no follow-up
    ("customer", "I was charged twice on my September bill, and this is the third time I call about it."),
    ("advisor", "Yes. Could you explain the problem again from the start?"),
    ("customer", "Again? I already told your colleagues everything."),
    ("advisor", "I will refund you one hundred and twenty dinars right away."),
    ("customer", "Okay, but I have heard that before."),
    ("advisor", "Please hold while I transfer you to the billing team."),
    ("customer", "Another transfer. Unbelievable. I am done, goodbye."),
]
SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "sample-call.wav"


@lru_cache(maxsize=1)
def sample_call() -> bytes:
    """Two channels, advisor left and customer right, about 35 seconds. Built once and kept on disk."""
    if SAMPLE_PATH.exists():
        return SAMPLE_PATH.read_bytes()
    parts, sr, t = [], 24000, 0.0
    for who, text in SAMPLE_SCRIPT:
        wav = voice.speak(text, "customer" if who == "customer" else "advisor", "ANGRY_PREMIUM" if who == "customer" else None, 25 if who == "customer" else 50)
        x, sr = sf.read(io.BytesIO(wav), dtype="float32")
        parts.append((who, int(t * sr), x))
        t += len(x) / sr + 0.8
    out = np.zeros((int(t * sr) + sr, 2), dtype="float32")
    for who, at, x in parts:
        out[at: at + len(x), 0 if who == "advisor" else 1] = x
    buf = io.BytesIO()
    sf.write(buf, out, sr, format="WAV", subtype="PCM_16")
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_PATH.write_bytes(buf.getvalue())
    return buf.getvalue()


def available() -> bool:
    return stt.available()
