"""Neural voice for the agents (Kokoro, Apache 2.0, runs offline through onnxruntime).

The model files live in models/voices/ (not in git, see services/agents/README.md). Without them the service still runs and
/voice/speak answers 503, and the web app falls back to the browser's own voices.
Kokoro does not act out emotions: the customer's mood changes the speaking speed only. Voices are fixed per persona.

Second engine, from Sami's Customer Simulator Agent (branch customer_agent, localtts.py): Piper voices run by sherpa-onnx, fully offline,
no PyTorch, ~63 MB a voice. Used when Kokoro's files are not there: the customer speaks with en_US-amy, the advisor with en_US-ryan,
loudness evened out as in Sami's code. Files in services/agents/models/piper/<voice>/ (not in git), package sherpa-onnx (requirements-models.txt).
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


PIPER_DIR = Path(os.environ.get("PIPER_DIR", Path(__file__).resolve().parent / "models" / "piper"))
PIPER_VOICES = {"customer": "vits-piper-en_US-amy-medium", "advisor": "vits-piper-en_US-ryan-medium"}
TARGET_RMS = 0.08            # Sami's loudness target: two voices of very different levels sound alike
_piper: dict = {}


def kokoro_available() -> bool:
    return MODEL.exists() and VOICES.exists()


def piper_available() -> bool:
    if not all((PIPER_DIR / v / "tokens.txt").exists() for v in PIPER_VOICES.values()):
        return False
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return False
    return True


def available() -> bool:
    return kokoro_available() or piper_available()


def engine_name() -> str | None:
    return "kokoro" if kokoro_available() else "piper" if piper_available() else None


def _piper_engine(role: str):
    name = PIPER_VOICES["customer" if role == "customer" else "advisor"]
    if name not in _piper:
        import sherpa_onnx
        d = PIPER_DIR / name
        onnx = next(d.glob("*.onnx"))
        cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(onnx), tokens=str(d / "tokens.txt"), data_dir=str(d / "espeak-ng-data")),
            num_threads=int(os.environ.get("VOICE_THREADS", 4)), provider="cpu"), max_num_sentences=1)
        _piper[name] = sherpa_onnx.OfflineTts(cfg)
    return _piper[name]


def _even_out(samples) -> np.ndarray:
    x = np.asarray(samples, dtype="float32")
    rms = float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
    if rms > 1e-6:
        x = x * (TARGET_RMS / rms)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    return x * (0.95 / peak) if peak > 0.95 else x


def _synthesize(text: str, role: str, voice: str, speed: float) -> tuple[np.ndarray, int]:
    if kokoro_available():
        return _engine().create(text, voice=voice, speed=speed, lang="en-us")
    audio = _piper_engine(role).generate(text, sid=0, speed=speed)
    return _even_out(audio.samples), audio.sample_rate


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
    key = (text, voice if kokoro_available() else role, speed)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        samples, rate = _synthesize(text, role, voice, speed)
        buf = io.BytesIO()
        sf.write(buf, np.asarray(samples), rate, format="WAV", subtype="PCM_16")
        _cache[key] = buf.getvalue()
        if len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
        return _cache[key]
