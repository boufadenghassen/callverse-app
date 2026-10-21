"""Speech to text for the advisor's voice notes (OpenAI Whisper base.en, English, runs offline on the GPU when there is one).

The model comes from the normal Hugging Face cache (see services/agents/README.md). Without it /voice/transcribe answers 503.
The web page sends a 16 kHz mono WAV (it converts the recording itself), so no ffmpeg is needed here.
"""
import io
import os
import threading

import librosa
import numpy as np
import soundfile as sf

MODEL_ID = os.environ.get("STT_MODEL", "openai/whisper-base.en")
SR = 16000
MAX_SECONDS = 60

_pipe = None
_lock = threading.Lock()


class BadAudio(ValueError):
    """The recording cannot be used: unreadable, silent or too short."""


def available() -> bool:
    from huggingface_hub import try_to_load_from_cache
    return isinstance(try_to_load_from_cache(MODEL_ID, "model.safetensors"), str)


def _pipeline():
    global _pipe
    if _pipe is None:
        import torch
        from transformers import pipeline
        gpu = torch.cuda.is_available()
        _pipe = pipeline("automatic-speech-recognition", model=MODEL_ID, device=0 if gpu else -1, dtype=torch.float16 if gpu else torch.float32)
    return _pipe


def load_audio(wav: bytes) -> np.ndarray:
    try:
        y, sr = sf.read(io.BytesIO(wav), dtype="float32", always_2d=True)
    except Exception:
        raise BadAudio("Could not read this recording.")
    y = y.mean(axis=1)
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    y = y[: MAX_SECONDS * SR]
    if len(y) < SR // 4 or float(np.abs(y).max()) < 0.005:
        raise BadAudio("I could not hear anything. Try again, closer to the microphone.")
    return y


def transcribe(wav: bytes) -> dict:
    y = load_audio(wav)
    with _lock:
        out = _pipeline()({"raw": y, "sampling_rate": SR}, chunk_length_s=30)
    return {"text": out["text"].strip(), "seconds": round(len(y) / SR, 1)}


def speech_segments(x: np.ndarray, min_gap: float = 0.6, min_len: float = 0.4) -> list[tuple[float, float]]:
    """Where somebody speaks in one channel: frames louder than a share of the channel's own loud level, joined across short pauses."""
    hop = int(SR * 0.03)
    rms = librosa.feature.rms(y=x, frame_length=hop * 2, hop_length=hop)[0]
    if rms.size == 0 or rms.max() < 0.005:
        return []
    loud = rms > max(0.004, 0.12 * float(np.percentile(rms, 95)))
    segs, start = [], None
    for i, on in enumerate(loud):
        if on and start is None:
            start = i
        if not on and start is not None:
            segs.append([start * hop / SR, i * hop / SR])
            start = None
    if start is not None:
        segs.append([start * hop / SR, len(loud) * hop / SR])
    joined: list[list[float]] = []
    for a, b in segs:
        if joined and a - joined[-1][1] < min_gap:
            joined[-1][1] = b
        else:
            joined.append([a, b])
    return [(a, b) for a, b in joined if b - a >= min_len]


def transcribe_segments(samples: np.ndarray) -> list[dict]:
    """Speech to text with times for one channel of a call (16 kHz mono float samples): [{text, start, end}], one per stretch of speech."""
    spans = speech_segments(samples)
    if not spans:
        return []
    pad = int(0.15 * SR)
    clips = [{"raw": samples[max(0, int(a * SR) - pad): int(b * SR) + pad].astype("float32"), "sampling_rate": SR} for a, b in spans]
    with _lock:
        out = _pipeline()(clips, batch_size=8, chunk_length_s=30)
    return [dict(text=o["text"].strip(), start=a, end=b) for (a, b), o in zip(spans, out) if o["text"].strip()]
