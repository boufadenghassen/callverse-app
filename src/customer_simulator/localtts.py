"""Voix locales (100 % hors-ligne) : modèles Piper exécutés par sherpa-onnx, une voix par persona.
Le mapping persona -> voix est dans data/voices.json ; les modèles sont téléchargés par download_voices.py."""
import glob
import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = Path(os.getenv("TTS_MODELS_DIR", ROOT / "models" / "tts"))
VOICES_FILE = ROOT / "data" / "voices.json"
TARGET_RMS = 0.08  # volume cible : harmonise des voix de niveaux très différents


class VoiceNotInstalled(RuntimeError):
    pass


def load_voice_table() -> dict:
    return json.loads(VOICES_FILE.read_text(encoding="utf-8"))


def voice_speed(base: float, emotion=None) -> float:
    """Un client énervé ou pressé parle plus vite (effet modeste, mais audible)."""
    if emotion is None:
        return base
    s = base * (1 + 0.30 * max(0.0, emotion.frustration - 0.3) + 0.15 * (emotion.urgency - 0.5))
    return max(0.9, min(1.3, s))


def normalize(samples, target_rms: float = TARGET_RMS):
    import numpy as np
    x = np.asarray(samples, dtype="float32")
    if len(x) == 0:
        return x
    rms = float(np.sqrt(np.mean(x * x)))
    if rms > 1e-6:
        x = x * (target_rms / rms)
    peak = float(np.max(np.abs(x)))
    return x * (0.95 / peak) if peak > 0.95 else x


class LocalTTS:
    def __init__(self, models_dir=None, table=None, threads=None):
        self.models_dir = Path(models_dir or MODELS_DIR)
        self.table = table if table is not None else load_voice_table()
        self.threads = threads or int(os.getenv("TTS_THREADS", min(4, os.cpu_count() or 2)))
        self._engines: dict = {}
        self._lock = threading.Lock()

    def entry(self, persona_id: str) -> dict:
        if persona_id not in self.table:
            raise KeyError(f"pas de voix définie pour '{persona_id}' dans data/voices.json")
        return self.table[persona_id]

    def is_installed(self, persona_id: str) -> bool:
        d = self.models_dir / self.entry(persona_id)["model"]
        return bool(glob.glob(str(d / "*.onnx")))

    def _engine(self, name: str):
        if name not in self._engines:
            d = self.models_dir / name
            onnx = sorted(glob.glob(str(d / "*.onnx")))
            if not onnx:
                raise VoiceNotInstalled(
                    f"voix '{name}' non installée dans {self.models_dir}. Lance : python download_voices.py")
            import sherpa_onnx  # pip install sherpa-onnx
            cfg = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=onnx[0], tokens=str(d / "tokens.txt"), data_dir=str(d / "espeak-ng-data")),
                    num_threads=self.threads, provider="cpu"),
                max_num_sentences=1)
            self._engines[name] = sherpa_onnx.OfflineTts(cfg)
        return self._engines[name]

    def warmup(self, persona_id: str) -> None:
        e = self.entry(persona_id)
        engine = self._engine(e["model"])
        with self._lock:
            engine.generate("Allô.", sid=e.get("sid", 0), speed=1.0)  # 1er appel plus lent : on le fait au démarrage

    def synth(self, persona_id: str, text: str, emotion=None):
        """-> (tableau mono float32, fréquence d'échantillonnage)"""
        e = self.entry(persona_id)
        engine = self._engine(e["model"])
        with self._lock:  # un seul calcul à la fois par moteur
            audio = engine.generate(text, sid=e.get("sid", 0), speed=voice_speed(e.get("speed", 1.0), emotion))
        return normalize(audio.samples, e.get("rms", TARGET_RMS)), audio.sample_rate
