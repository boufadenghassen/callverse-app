"""Speech to text for the advisor's voice notes (OpenAI Whisper base.en, English, runs offline on the GPU when there is one).

The model comes from the normal Hugging Face cache (see services/agents/README.md). Without it /voice/transcribe answers 503.
The web page sends a 16 kHz mono WAV (it converts the recording itself), so no ffmpeg is needed here.

Second engine, from Sami's Customer Simulator Agent (branch customer_agent): faster-whisper (CTranslate2, int8 on the CPU, no PyTorch),
used when transformers/torch or the cached model are missing. Its model (Systran/faster-whisper-base.en, ~150 MB) is downloaded into the
Hugging Face cache the first time; package faster-whisper (requirements-models.txt).
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


FAST_MODEL = os.environ.get("STT_FAST_MODEL", "base.en")
_fast = None


def transformers_available() -> bool:
    from huggingface_hub import try_to_load_from_cache
    if not isinstance(try_to_load_from_cache(MODEL_ID, "model.safetensors"), str):
        return False
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


def fast_available() -> bool:
    if os.environ.get("STT_FAST", "1") == "0":
        return False
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def available() -> bool:
    return transformers_available() or fast_available()


def _fast_model():
    global _fast
    if _fast is None:
        from faster_whisper import WhisperModel
        _fast = WhisperModel(FAST_MODEL, device="cpu", compute_type="int8")
    return _fast


def warm() -> None:
    """Load (and the first time, download) the speech-to-text model at start-up."""
    _pipeline() if transformers_available() else _fast_model()


def _texts(clips: list[np.ndarray]) -> list[str]:
    """Speech to text for a few clips of 16 kHz mono float samples, with whichever engine is installed."""
    if transformers_available():
        out = _pipeline()([{"raw": c, "sampling_rate": SR} for c in clips], batch_size=8, chunk_length_s=30)
        return [o["text"].strip() for o in out]
    texts = []
    for c in clips:
        segments, _ = _fast_model().transcribe(c.astype("float32"), language="en", beam_size=1, vad_filter=False)
        texts.append(" ".join(seg.text.strip() for seg in segments).strip())
    return texts


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
        text = _texts([y])[0]
    return {"text": text, "seconds": round(len(y) / SR, 1)}


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
    clips = [samples[max(0, int(a * SR) - pad): int(b * SR) + pad].astype("float32") for a, b in spans]
    with _lock:
        texts = _texts(clips)
    return [dict(text=t, start=a, end=b) for (a, b), t in zip(spans, texts) if t]
