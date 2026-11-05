import sys
sys.path.insert(0, "src")
from customer_simulator.voice import Endpointer, split_sentences


def run(ep, seq):
    """Comme listen_auto : on s'arrête au premier 'end' ou 'timeout'."""
    out = []
    for i, r in enumerate(seq):
        e = ep.feed(r)
        if e:
            out.append((i, e))
            if e in ("end", "timeout"):
                break
    return out


def test_endpointer_start_and_end():
    ep = Endpointer(block_s=0.1, silence_s=1.0, min_speech_s=0.25, calib_s=0.4)
    seq = [0.001] * 4 + [0.001] * 3 + [0.1] * 8 + [0.001] * 12
    ev = run(ep, seq)
    assert [e for _, e in ev] == ["start", "end"]
    assert ev[0][0] == 4 + 3 + 2          # 3e bloc fort consécutif
    assert ev[1][0] == 4 + 3 + 8 + 9      # 10e bloc de silence


def test_endpointer_ignores_short_noise():
    ep = Endpointer(block_s=0.1, calib_s=0.4, start_timeout_s=3.0)
    seq = [0.001] * 4 + [0.1, 0.001] * 5 + [0.001] * 30
    assert [e for _, e in run(ep, seq)] == ["timeout"]


def test_endpointer_brief_pause_does_not_cut():
    ep = Endpointer(block_s=0.1, silence_s=1.0, calib_s=0.4)
    seq = [0.001] * 4 + [0.1] * 5 + [0.001] * 5 + [0.1] * 5 + [0.001] * 12
    assert [e for _, e in run(ep, seq)] == ["start", "end"]  # une seule phrase, pause de 0,5 s tolérée


def test_split_sentences():
    out = split_sentences("Allô ? Ça fait trois jours que ma ligne ne marche pas. Je veux une réponse.")
    assert len(out) == 2 and out[0].startswith("Allô ? Ça fait")
    assert split_sentences("Bonjour") == ["Bonjour"]


def test_to_np_all_shapes():
    import numpy as np
    from customer_simulator.voice import _to_np
    for shape in [(1000,), (1, 1000), (1000, 1), (2, 1000), (1000, 2)]:
        out = _to_np(np.random.rand(*shape))
        assert out.ndim == 1 and len(out) == 1000, shape


def test_voxcpm_modes(monkeypatch):
    import numpy as np
    from customer_simulator.voice import Voice

    class FakeTTS:
        sample_rate = 48000

    class FakeModel:
        tts_model = FakeTTS()
        def __init__(self): self.calls = []
        def generate(self, text): self.calls.append(text); return np.zeros(100, dtype="float32")
        def generate_streaming(self, text):
            for _ in range(3): yield np.zeros(10, dtype="float32")

    v = Voice(tts="voxcpm"); v._vox = FakeModel()
    txt = "Premiere phrase assez longue ici. Deuxieme phrase assez longue aussi."
    monkeypatch.setenv("VOX_MODE", "sentence")
    assert len(list(v._voxcpm_chunks(txt))) == 2
    monkeypatch.setenv("VOX_MODE", "full")
    assert len(list(v._voxcpm_chunks(txt))) == 1
    monkeypatch.setenv("VOX_MODE", "stream")
    assert len(list(v._voxcpm_chunks(txt))) == 3
    assert all(c.startswith("(Tunisian Dialect)") for c in v._vox.calls)


def test_threshold_adapts_when_echo_fades():
    """Écho fort pendant la calibration : le seuil est plafonné, puis redescend quand l'écho retombe."""
    ep = Endpointer(block_s=0.1, calib_s=0.4, min_speech_s=0.25)
    seq = [0.1] * 4 + [0.001] * 20 + [0.05] * 4   # 0.05 est sous le plafond de 0.06 mais détectable une fois adapté
    ev = run(ep, seq)
    assert [e for _, e in ev] == ["start"]
    assert ep.threshold <= 0.06


def test_threshold_is_capped():
    ep = Endpointer(block_s=0.1, calib_s=0.4)
    for _ in range(30):
        ep.feed(0.5)  # bruit constant très fort
    assert ep.threshold == ep.max_threshold
