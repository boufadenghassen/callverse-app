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
