import sys
sys.path.insert(0, "src")
import numpy as np
import pytest
from customer_simulator import CustomerSimulatorAgent, Scenario
from customer_simulator.live import DuplexListener, iter_sentences
from customer_simulator.llm import MockLLM
from customer_simulator.voice import Voice


# ---------- découpage en phrases ----------
def test_iter_sentences_splits_as_text_arrives():
    pieces = ["Bonjour, j'ai un pro", "blème avec ma factu", "re. Je ne comprends ", "pas pourquoi ! Merci."]
    assert list(iter_sentences(pieces)) == ["Bonjour, j'ai un problème avec ma facture.",
                                            "Je ne comprends pas pourquoi !", "Merci."]


def test_iter_sentences_merges_short_ones_and_flushes_tail():
    assert list(iter_sentences(["Allô ? Ça fait trois jours que ça ne marche pas", " du tout"])) == \
        ["Allô ? Ça fait trois jours que ça ne marche pas du tout"]


# ---------- réponse en flux de l'agent ----------
class StreamLLM(MockLLM):
    def stream(self, system, messages, max_tokens=300):
        for piece in ["Je veux ", "un rembours", "ement. Tout de suite."]:
            yield piece


def test_reply_stream_full_and_interrupted():
    ag = CustomerSimulatorAgent(StreamLLM())
    rs = ag.start_stream(Scenario(persona_id="fr_m", seed=1))
    assert "".join(rs.pieces()) == "Je veux un remboursement. Tout de suite."
    m = rs.finish()
    assert m.text.startswith("Je veux") and ag.turn == 1 and ag.history[-1]["role"] == "assistant"

    rs = ag.reply_stream("Un instant madame, je regarde votre dossier.", interrupted=True)
    assert "couper la parole" in ag.history[-1]["content"]          # le client sait qu'on l'a coupé
    m = rs.finish(spoken="Je veux un remboursement.")                 # seule la 1re phrase a été dite
    assert m.text == "Je veux un remboursement." and ag.history[-1]["content"] == m.text


def test_reply_stream_falls_back_without_streaming_backend():
    ag = CustomerSimulatorAgent(MockLLM())
    rs = ag.start_stream(Scenario(persona_id="en_f", seed=1))
    assert list(rs.pieces()) and rs.finish().text


# ---------- lecture en flux, interruptible ----------
class FakeLocal:
    def synth(self, pid, text, emotion=None):
        return np.full(16000, 0.1, dtype="float32"), 16000  # 1 s par phrase


class Sink:
    def __init__(self): self.writes, self.aborted = 0, None
    def write(self, block): self.writes += 1
    def close(self, abort=False): self.aborted = abort


def make_voice():
    v, sink = Voice(tts="local"), Sink()
    v.local, v.sink_factory = FakeLocal(), lambda sr, lat: sink
    return v, sink


def test_speak_stream_plays_everything():
    v, sink = make_voice()
    shown = []
    interrupted, played = v.speak_stream(iter(["Bonjour monsieur.", "Je vous écoute."]), "fr", "M", "fr_m",
                                         on_sentence=shown.append)
    assert not interrupted and played == shown == ["Bonjour monsieur.", "Je vous écoute."]
    assert sink.writes == 40 and sink.aborted is False


def test_speak_stream_can_be_cut_instantly():
    v, sink = make_voice()
    n = {"c": 0}

    def stop():
        n["c"] += 1
        return n["c"] > 30  # coupé dans la 2e phrase

    interrupted, played = v.speak_stream(iter(["Première phrase ici.", "Deuxième phrase là."]), "fr", "F", "fr_f",
                                         should_stop=stop)
    assert interrupted and sink.aborted is True and played[0] == "Première phrase ici."
    assert sink.writes < 40


def test_speak_stream_off_returns_text_only():
    v = Voice(tts="off")
    assert v.speak_stream(iter(["Salut.", "Ça va ?"]), "fr", "F") == (False, ["Salut.", "Ça va ?"])


# ---------- écoute permanente / coupure de parole ----------
def blocks(listener, amp, n):
    for _ in range(n):
        listener._process_block(np.full(listener.block, amp, dtype="float32"))


def make_listener(**kw):
    ln = DuplexListener(silence_s=0.8, **kw)
    ln.phase = "calib0"
    blocks(ln, 0.002, 25)   # bruit ambiant au calme
    ln.phase = "idle"
    return ln


def test_barge_in_then_capture_until_silence():
    ln = make_listener()
    ln.begin_playback()
    blocks(ln, 0.002, 30)                     # le client parle, tu te tais
    assert not ln.barged.is_set()
    blocks(ln, 0.12, 14)                      # tu parles par-dessus
    assert ln.barged.is_set() and ln.phase == "speech"
    ln.end_playback()                          # sans effet : la capture continue
    blocks(ln, 0.12, 20)
    blocks(ln, 0.002, 30)                     # silence : fin de ta phrase
    audio, waited = ln.result
    assert ln.done.is_set() and audio is not None and len(audio) > 30 * ln.block and waited == 0.0


def test_listen_after_client_finished():
    ln = make_listener()
    ln.begin_playback()
    blocks(ln, 0.002, 20)
    ln.end_playback()
    assert ln.phase == "listen"
    blocks(ln, 0.002, 10)
    blocks(ln, 0.1, 20)
    assert ln.phase == "speech" and not ln.barged.is_set()
    blocks(ln, 0.002, 30)
    audio, waited = ln.result
    assert audio is not None and waited >= 0.0


def test_listen_timeout_returns_none():
    ln = make_listener(start_timeout_s=1.0)
    ln.begin_playback()
    ln.end_playback()
    blocks(ln, 0.002, 60)
    assert ln.done.is_set() and ln.result == (None, None)
