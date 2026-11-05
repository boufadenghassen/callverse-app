"""Interactivité en direct : découpage du texte en phrases au fil de l'eau, et écoute permanente du micro
(coupure de parole pendant que le client parle, puis capture de ta phrase)."""
import collections
import os
import queue
import re
import threading
import time

from .voice import Endpointer

SENT_END = re.compile(r"[.!?…]+[\"'»)]*\s")


def iter_sentences(pieces, min_len: int = 14):
    """Reçoit des morceaux de texte (tokens du LLM) et rend des phrases complètes dès qu'elles sont finies.
    Les phrases très courtes sont regroupées avec la suivante."""
    buf = ""
    for piece in pieces:
        buf += piece
        while True:
            cut = next((m.end() for m in SENT_END.finditer(buf) if m.end() >= min_len), None)
            if cut is None:
                break
            yield buf[:cut].strip()
            buf = buf[cut:]
    if buf.strip():
        yield buf.strip()


class DuplexListener:
    """Écoute le micro EN CONTINU. Phases d'un tour :
      play   : le client parle. Si tu parles par-dessus (casque conseillé), `barged` s'allume et la capture démarre.
      listen : le client a fini ; on attend que tu commences.
      speech : ta phrase est capturée jusqu'au silence.
    wait_utterance() rend alors (audio, secondes d'attente) ; (None, None) si tu n'as rien dit."""

    def __init__(self, silence_s: float | None = None, start_timeout_s: float = 30.0,
                 block_s: float = 0.032, sr: int = 16000):
        self.sr, self.block_s, self.block = sr, block_s, int(sr * block_s)
        self.silence_s = silence_s or float(os.getenv("VAD_SILENCE", "0.8"))
        self.start_timeout_s = start_timeout_s
        self.q: queue.Queue = queue.Queue()
        self.lock = threading.RLock()
        self.stream = None
        self.thread = None
        self._stop = threading.Event()
        self.noise: list[float] = []
        self.last_block_t = time.time()
        self.barged = threading.Event()
        self.done = threading.Event()
        self.phase = "idle"
        self.ep: Endpointer | None = None
        self.ring: collections.deque = collections.deque(maxlen=int(1.0 / block_s))
        self.chunks: list = []
        self.waited = 0.0
        self.result: tuple = (None, None)
        self.t_listen0 = 0.0

    # ---- cycle de vie ----
    def open(self) -> None:
        import sounddevice as sd

        def cb(indata, frames, t, status):
            self.q.put(indata[:, 0].copy())

        self.phase = "calib0"
        self.stream = sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                                     blocksize=self.block, callback=cb)
        self.stream.start()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        time.sleep(0.7)  # mesure le bruit ambiant au calme, avant que le client ne parle
        self.phase = "idle"

    def close(self) -> None:
        self._stop.set()
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                b = self.q.get(timeout=0.3)
            except queue.Empty:
                continue
            self._process_block(b)

    # ---- tour de parole ----
    def _barge_ep(self) -> Endpointer:  # seuil plus haut : ne réagit pas au moindre bruit ni à l'écho
        return Endpointer(block_s=self.block_s, silence_s=self.silence_s, min_speech_s=0.35,
                          start_timeout_s=3600.0, calib_s=0.3, min_threshold=0.03,
                          max_threshold=0.12, factor=4.0)

    def _listen_ep(self) -> Endpointer:
        return Endpointer(block_s=self.block_s, silence_s=self.silence_s,
                          start_timeout_s=self.start_timeout_s, calib_s=0.3)

    @staticmethod
    def _prime(ep: Endpointer, values) -> None:
        if values:
            ep.adopt(values)
        else:
            ep.state, ep.count = "wait", 0

    def begin_playback(self) -> None:
        with self.lock:
            self.barged.clear()
            self.done.clear()
            self.result, self.chunks, self.waited = (None, None), [], 0.0
            self.ring = collections.deque(maxlen=int(1.0 / self.block_s))
            self.ep = self._barge_ep()
            self._prime(self.ep, self.noise)
            self.phase = "play"

    def end_playback(self) -> None:
        with self.lock:
            if self.phase != "play":
                return  # coupure de parole : la capture est déjà en cours
            self.noise = list(self.ep.window) or self.noise
            self.ep = self._listen_ep()
            self._prime(self.ep, self.noise)
            self.ring = collections.deque(maxlen=int(0.6 / self.block_s))  # petit préroll, sans l'écho du client
            self.t_listen0 = time.time()
            self.phase = "listen"

    def wait_utterance(self, timeout: float | None = None) -> tuple:
        t0 = time.time()
        while not self.done.wait(0.3):
            if time.time() - self.last_block_t > 3.0:
                raise RuntimeError("le micro ne fournit aucun son (occupé, débranché ou utilisé par une autre application)")
            if timeout and time.time() - t0 > timeout:
                return None, None
        return self.result

    def _finish(self, result: tuple) -> None:
        self.result = result
        self.noise = list(self.ep.window) or self.noise
        self.phase = "idle"
        self.done.set()

    def _process_block(self, b) -> None:
        import numpy as np
        rms = float(np.sqrt(np.mean(b * b)))
        with self.lock:
            self.last_block_t = time.time()
            if self.phase == "calib0":
                self.noise.append(rms)
            elif self.phase == "play":
                self.ring.append(b)
                ev = self.ep.feed(rms)
                if self.ep.state == "wait":
                    self.ep.count = 0  # pas de délai d'attente pendant que le client parle
                if ev == "start":  # tu parles par-dessus le client
                    self.barged.set()
                    self.chunks, self.waited, self.phase = list(self.ring), 0.0, "speech"
            elif self.phase == "listen":
                self.ring.append(b)
                ev = self.ep.feed(rms)
                if ev == "start":
                    self.chunks, self.phase = list(self.ring), "speech"
                    self.waited = max(0.0, time.time() - self.t_listen0 - self.ep.min_speech_s)
                elif ev == "timeout":
                    self._finish((None, None))
            elif self.phase == "speech":
                self.chunks.append(b)
                if self.ep.feed(rms) == "end":
                    self._finish((np.concatenate(self.chunks), self.waited))
