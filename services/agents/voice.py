"""Neural voice for the agents (Kokoro, Apache 2.0, runs offline through onnxruntime).

The model files live in models/voices/ (not in git, see services/agents/README.md). Without them the service still runs and
/voice/speak answers 503, and the web app falls back to the browser's own voices.
Kokoro does not act out emotions: the customer's mood changes the speaking speed only. Voices are fixed per persona.
"""
import io
import os
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np
import soundfile as sf

VOICES_DIR = Path(os.environ.get("VOICES_DIR", Path(__file__).resolve().parents[2] / "models" / "voices"))
MODEL, VOICES = VOICES_DIR / "kokoro-v1.0.onnx", VOICES_DIR / "voices-v1.0.bin"

ADVISOR_VOICE = "am_michael"
CUSTOMER_VOICES = {   # one recognisable voice per persona
    "IMPATIENT": "af_nova", "ANXIOUS": "af_sky", "ANGRY_PREMIUM": "af_bella", "LOYAL_AT_RISK": "af_heart", "NEW_SUBSCRIBER": "af_nicole",
}
DEFAULT_CUSTOMER_VOICE = "af_nicole"

_kokoro = None
_lock = threading.Lock()   # onnxruntime sessions are fine to share, but one synthesis at a time keeps latency predictable
_cache: "OrderedDict[tuple, bytes]" = OrderedDict()
CACHE_SIZE = 64


def available() -> bool:
    return MODEL.exists() and VOICES.exists()


def _engine():
    global _kokoro
    if _kokoro is None:
        import onnxruntime as ort
        from kokoro_onnx import Kokoro
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(os.environ.get("VOICE_THREADS", 4))   # measured on a 12-thread laptop: 4 is fastest, 12 is twice as slow
        so.inter_op_num_threads = 1
        _kokoro = Kokoro.from_session(ort.InferenceSession(str(MODEL), sess_options=so, providers=["CPUExecutionProvider"]), str(VOICES))
    return _kokoro


def speed_for(mood: int) -> float:
    """An upset customer (low mood) talks faster, a content one slower: 1.2 at mood 0, 0.85 at mood 100."""
    return round(max(0.85, min(1.2, 1 + (50 - max(0, min(100, mood))) / 250)), 2)


def voice_for(role: str, persona: str | None) -> str:
    return ADVISOR_VOICE if role == "advisor" else CUSTOMER_VOICES.get(persona or "", DEFAULT_CUSTOMER_VOICE)


def speak(text: str, role: str = "advisor", persona: str | None = None, mood: int = 50) -> bytes:
    """The text as a 16-bit mono WAV."""
    voice, speed = voice_for(role, persona), speed_for(mood) if role == "customer" else 1.0
    key = (text, voice, speed)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        samples, rate = _engine().create(text, voice=voice, speed=speed, lang="en-us")
        buf = io.BytesIO()
        sf.write(buf, np.asarray(samples), rate, format="WAV", subtype="PCM_16")
        _cache[key] = buf.getvalue()
        if len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
        return _cache[key]
