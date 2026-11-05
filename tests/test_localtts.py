import os
import sys
sys.path.insert(0, "src")
import numpy as np
import pytest
from customer_simulator.localtts import LocalTTS, VoiceNotInstalled, normalize, voice_speed
from customer_simulator.schemas import EmotionState


def test_voice_speed_rises_with_frustration_and_is_bounded():
    calm, angry = EmotionState(frustration=0.1), EmotionState(frustration=1.0, urgency=1.0)
    assert voice_speed(1.0, calm) <= 1.0 + 1e-9 < voice_speed(1.0, angry) <= 1.3
    assert voice_speed(1.0, None) == 1.0


def test_normalize_levels_and_clips():
    quiet = normalize(np.random.randn(8000) * 0.01)
    assert abs(float(np.sqrt((quiet ** 2).mean())) - 0.08) < 0.01
    assert float(np.abs(normalize(np.random.randn(8000) * 5)).max()) <= 0.95 + 1e-6
    assert len(normalize([])) == 0


def test_every_persona_has_a_voice():
    from customer_simulator.generator import load_personas
    t = LocalTTS(models_dir="/nonexistent")
    for pid in ("fr_f", "fr_m", "en_f", "en_m"):
        assert t.entry(pid)["model"]
    with pytest.raises(VoiceNotInstalled):
        t.synth("fr_f", "Bonjour")


installed = bool(os.getenv("TTS_MODELS_DIR")) and LocalTTS().is_installed("fr_m") if os.getenv("TTS_MODELS_DIR") else False


@pytest.mark.skipif(not installed, reason="voix non installées (python download_voices.py)")
@pytest.mark.parametrize("pid", ["fr_f", "fr_m", "en_f", "en_m"])
def test_real_voices_synthesize(pid):
    audio, sr = LocalTTS().synth(pid, "Hello, this is a test. Bonjour, ceci est un test.")
    assert sr >= 16000 and len(audio) > sr * 1.0
    assert 0.05 < float(np.sqrt((audio ** 2).mean())) < 0.12 and float(np.abs(audio).max()) <= 0.951
