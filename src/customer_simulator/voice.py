"""Voix : TTS locale (voix du client), STT (ta voix) et écoute mains libres.
Dépendances dans requirements-voice.txt, importées à la demande."""
import asyncio
import collections
import math
import os
import queue
import re
import tempfile
import threading
import time

from .localtts import LocalTTS, VoiceNotInstalled

VOICES = {  # voix en ligne (edge-tts), optionnelles : --tts edge
    ("fr", "F"): "fr-FR-DeniseNeural", ("fr", "M"): "fr-FR-HenriNeural",
    ("en", "F"): "en-GB-SoniaNeural", ("en", "M"): "en-GB-RyanNeural",
    ("derja", "F"): "ar-TN-ReemNeural", ("derja", "M"): "ar-TN-HediNeural",
}
WHISPER_LANG = {"fr": "fr", "en": "en", "derja": "ar"}
SR = 16000

TO_ARABIC_SYSTEM = (
    "Convertis ce texte tunisien écrit en arabizi (alphabet latin) en derja tunisienne "
    "écrite en alphabet arabe. Garde les mots français en lettres latines. "
    "Réponds UNIQUEMENT avec le texte converti, sans explication."
)


def make_arabic_converter(llm):
    """arabizi -> alphabet arabe via le LLM (derja, en pause pour l'instant)."""
    def convert(text: str) -> str:
        try:
            out = llm.complete(TO_ARABIC_SYSTEM, [{"role": "user", "content": text}], 200).strip()
            return out or text
        except Exception:
            return text
    return convert


def split_sentences(text: str, min_len: int = 12) -> list[str]:
    """Découpe en phrases (les très courtes sont fusionnées) pour jouer la 1re sans attendre le reste."""
    out: list[str] = []
    for part in re.split(r"(?<=[.!?؟…])\s+", text.strip()):
        part = part.strip()
        if not part:
            continue
        if out and len(out[-1]) < min_len:
            out[-1] += " " + part
        else:
            out.append(part)
    return out or [text.strip()]


class Endpointer:
    """Détecte début et fin de parole à partir de l'énergie (RMS) de blocs audio.
    Le seuil s'adapte en continu au bruit ambiant (écho de la voix du client qui retombe, ventilateur...)
    et est plafonné pour qu'un bruit passager ne rende jamais ta voix indétectable.
    Indépendant du micro, donc testable. feed(rms) -> None | 'start' | 'end' | 'timeout'."""

    def __init__(self, block_s=0.032, silence_s=1.0, min_speech_s=0.25, start_timeout_s=30.0,
                 max_s=25.0, calib_s=0.4, min_threshold=0.012, max_threshold=0.06, factor=3.0):
        n = lambda sec: max(1, math.ceil(sec / block_s - 1e-9))
        self.block_s, self.min_speech_s = block_s, min_speech_s
        self.n_calib, self.n_min_speech = n(calib_s), n(min_speech_s)
        self.n_silence, self.n_timeout, self.n_max = n(silence_s), n(start_timeout_s), n(max_s)
        self.min_threshold, self.max_threshold, self.factor = min_threshold, max_threshold, factor
        self.threshold = min_threshold
        self.window: collections.deque = collections.deque(maxlen=n(1.5))
        self.state, self.count, self.loud, self.quiet, self.total = "calib", 0, 0, 0, 0
        self.noise: list[float] = []

    def _retune(self) -> None:
        vals = sorted(self.window)
        if not vals:
            return
        est = vals[int(0.2 * (len(vals) - 1))]  # bruit de fond = bas du dernier 1,5 s
        self.threshold = min(self.max_threshold, max(self.min_threshold, self.factor * est))

    def adopt(self, values) -> None:
        """Reprend un bruit ambiant déjà mesuré : pas de calibration à refaire."""
        self.window.clear()
        self.window.extend(values)
        self._retune()
        self.state, self.count = "wait", 0

    def feed(self, rms: float):
        if self.state == "calib":
            self.noise.append(rms)
            if len(self.noise) >= self.n_calib:
                self.adopt(self.noise)
            return None
        if self.state == "wait":
            self.count += 1
            self.window.append(rms)
            self._retune()
            self.loud = self.loud + 1 if rms > self.threshold else 0
            if self.loud >= self.n_min_speech:
                self.state, self.quiet, self.total = "speech", 0, self.loud
                return "start"
            return "timeout" if self.count >= self.n_timeout else None
        self.total += 1  # état "speech" : seuil figé
        self.quiet = 0 if rms > self.threshold else self.quiet + 1
        if self.quiet >= self.n_silence or self.total >= self.n_max:
            return "end"
        return None


def _to_np(x):
    """Tout format (tensor, (N,), (1,N), (N,1), (canaux,N)...) -> tableau mono 1-D float32."""
    import numpy as np
    if hasattr(x, "detach"):
        x = x.detach().cpu().numpy()
    a = np.squeeze(np.asarray(x, dtype="float32"))
    if a.ndim > 1:
        a = a.mean(axis=0 if a.shape[0] < a.shape[1] else 1)
    return np.atleast_1d(a)


class _SDSink:
    """Sortie audio (haut-parleurs / casque) via sounddevice."""

    def __init__(self, sr: int, latency: str = "high"):
        import sounddevice as sd
        self.stream = sd.OutputStream(samplerate=sr, channels=1, dtype="float32", latency=latency)
        self.stream.start()

    def write(self, block) -> None:
        self.stream.write(block.reshape(-1, 1))

    def close(self, abort: bool = False) -> None:
        try:
            self.stream.abort() if abort else self.stream.stop()  # abort = coupe net, sans finir le tampon
        finally:
            self.stream.close()


class Voice:
    def __init__(self, stt_model=None, device=None, compute_type=None, tts=None, arabic_converter=None):
        self.stt_model_name = stt_model or os.getenv("STT_MODEL")  # None = auto : base.en (EN) / base (FR)
        self.device = device or os.getenv("STT_DEVICE", "cpu")
        self.compute_type = compute_type or os.getenv("STT_COMPUTE", "int8")
        self.tts = tts or os.getenv("TTS_BACKEND", "local")        # local | edge | sapi | voxcpm | off
        self.local = LocalTTS()
        self.sink_factory = lambda sr, latency: _SDSink(sr, latency)  # remplaçable (tests)
        self.vox_model = os.getenv("VOXCPM_MODEL", "Code-Quasar/voxcpm-tn")
        self.vox_device = os.getenv("VOXCPM_DEVICE", "cuda")
        self.arabic_converter = arabic_converter
        self._whisper: dict = {}
        self._vox = None
        self._vox_sr = 48000
        self.last_stt_s = 0.0
        self.last_first_audio_s = 0.0
        self._t_speak0 = 0.0

    # ---------------- préchauffage ----------------
    def warmup(self, language: str = "fr", persona_id: str | None = None) -> None:
        """Charge les modèles au démarrage pour que le 1er tour ne soit pas lent."""
        self._get_whisper(language)
        if self.tts == "local":
            try:
                self.local.warmup(persona_id or f"{language}_f")
            except VoiceNotInstalled as e:
                print(f"  [voix locale absente] {e}\n  -> la conversation continue sans la voix du client.")
                self.tts = "off"
            except Exception as e:
                print(f"  [voix locale indisponible : {type(e).__name__}: {e}]\n"
                      "  -> as-tu fait : python -m pip install sherpa-onnx ?  La conversation continue sans voix.")
                self.tts = "off"
        elif self.tts == "voxcpm":
            try:
                self._load_voxcpm()
            except Exception as e:
                self._fallback(e)

    def _fallback(self, err: Exception) -> None:
        print(f"  [VoxCPM indisponible ({type(err).__name__}: {str(err)[:150]}) -> repli sur la voix locale]")
        self.tts = "local"

    # ---------------- sortie : le client parle ----------------
    def speak(self, text: str, language: str, gender: str, persona_id: str | None = None, emotion=None) -> None:
        if self.tts == "off":
            return
        if language == "derja" and self.arabic_converter and self.tts in ("edge", "voxcpm"):
            text = self.arabic_converter(text)
        try:
            self._speak_converted(text, language, gender, persona_id, emotion)
        except Exception as e:
            if self.tts != "voxcpm":
                raise
            self._fallback(e)
            self._speak_converted(text, language, gender, persona_id, emotion)

    def _speak_converted(self, text, language, gender, persona_id=None, emotion=None) -> None:
        if self.tts in ("local", "edge"):
            self.speak_stream(split_sentences(text), language, gender, persona_id, emotion)
            return
        if self.tts == "sapi":
            return self._speak_sapi(text, language)
        # voxcpm : ancien chemin (génération phrase par phrase, lecture continue)
        self._t_speak0 = time.time()
        q: queue.Queue = queue.Queue(maxsize=16)
        errors: list[Exception] = []

        def producer():
            try:
                for item in self._voxcpm_chunks(text):
                    q.put(item)
            except Exception as e:
                errors.append(e)
            finally:
                q.put(None)

        th = threading.Thread(target=producer, daemon=True)
        th.start()
        self._play_queue(q)
        th.join()
        if errors:
            raise errors[0]

    def _synth_sentence(self, sentence, language, gender, persona_id, emotion):
        if self.tts == "local":
            return self.local.synth(persona_id or f"{language}_{gender.lower()}", sentence, emotion)
        if self.tts == "edge":
            return self._edge_synth(sentence, VOICES[(language, gender)])
        raise RuntimeError(f"backend vocal '{self.tts}' non géré en flux")

    def _play_blocks(self, sink, data, sr: int, stop) -> tuple[bool, float]:
        """Joue par blocs de 50 ms pour pouvoir s'arrêter net. -> (terminé ?, fraction jouée)"""
        n, i = max(1, int(0.05 * sr)), 0
        while i < len(data):
            if stop():
                return False, i / len(data)
            sink.write(data[i:i + n])
            i += n
        return True, 1.0

    def speak_stream(self, sentences, language: str, gender: str, persona_id: str | None = None,
                     emotion=None, should_stop=None, on_sentence=None) -> tuple[bool, list[str]]:
        """Joue des phrases (itérable, éventuellement produit par le LLM au fil de l'eau) :
        la 1re est jouée pendant que la suivante est générée puis synthétisée.
        should_stop() -> True coupe le son immédiatement (coupure de parole).
        Retourne (interrompu, phrases réellement jouées)."""
        stop = should_stop or (lambda: False)
        sentences = iter(sentences)
        if self.tts in ("off", "sapi", "voxcpm"):  # pas de lecture en flux : on consomme, puis on lit d'un bloc
            played: list[str] = []
            for s in sentences:
                played.append(s)
                if on_sentence:
                    on_sentence(s)
            if played and self.tts in ("sapi", "voxcpm"):
                self.speak(" ".join(played), language, gender, persona_id, emotion)
            return False, played

        t0 = time.time()
        q: queue.Queue = queue.Queue(maxsize=3)
        cancel = threading.Event()
        errors: list[Exception] = []
        producer_stopped = [False]

        def put(item):
            while not cancel.is_set():
                try:
                    q.put(item, timeout=0.1)
                    return
                except queue.Full:
                    pass

        def producer():
            try:
                for s in sentences:
                    if cancel.is_set() or stop():
                        producer_stopped[0] = True
                        break
                    if not s.strip():
                        continue
                    data, sr = self._synth_sentence(s, language, gender, persona_id, emotion)
                    put((s, data, sr))
            except Exception as e:
                errors.append(e)
            finally:
                put(None)

        th = threading.Thread(target=producer, daemon=True)
        th.start()
        played, sink, interrupted = [], None, False
        try:
            while True:
                item = q.get()
                if item is None:
                    break
                s, data, sr = item
                if sink is None:
                    self.last_first_audio_s = time.time() - t0
                    sink = self.sink_factory(sr, "low" if should_stop else "high")
                if on_sentence:
                    on_sentence(s)
                done, frac = self._play_blocks(sink, _to_np(data), sr, stop)
                if done:
                    played.append(s)
                else:
                    interrupted = True
                    if frac >= 0.5:  # dite à moitié : le client s'en souvient
                        played.append(s)
                    break
        finally:
            cancel.set()
            if sink is not None:
                sink.close(abort=interrupted)
            th.join(timeout=0.5)
        if errors and not played:
            raise errors[0]
        return interrupted or producer_stopped[0], played

    # ---------------- voix en ligne (optionnel) ----------------
    def _edge_synth(self, text: str, voice: str):
        import edge_tts, soundfile as sf
        path = os.path.join(tempfile.gettempdir(), f"callverse_{threading.get_ident()}.mp3")
        asyncio.run(edge_tts.Communicate(text, voice).save(path))
        data, sr = sf.read(path, dtype="float32")
        return data, sr

    # ---------------- VoxCPM (derja, en pause) ----------------
    def _play_queue(self, q: queue.Queue) -> None:
        import numpy as np
        stream_sink, sr_used, played = None, None, []
        try:
            while True:
                item = q.get()
                if item is None:
                    break
                data, sr = item
                data = _to_np(data)
                played.append(data)
                if stream_sink is None:
                    self.last_first_audio_s = time.time() - self._t_speak0
                    stream_sink = self.sink_factory(sr, "high")
                    sr_used = sr
                stream_sink.write(data)
        finally:
            if stream_sink is not None:
                stream_sink.close()
            if played and os.getenv("VOX_DEBUG_WAV"):
                import soundfile as sf
                os.makedirs("debug_audio", exist_ok=True)
                sf.write(f"debug_audio/reply_{int(time.time())}.wav", np.concatenate(played), sr_used)

    def _load_voxcpm(self):
        if self._vox is None:
            from voxcpm import VoxCPM
            print(f"  (chargement de VoxCPM sur '{self.vox_device}', 1re fois seulement...)")
            self._vox = VoxCPM.from_pretrained(self.vox_model, load_denoiser=False, device=self.vox_device)
            self._vox_sr = self._vox.tts_model.sample_rate
        return self._vox

    def _voxcpm_chunks(self, text: str):
        """VOX_MODE : sentence (défaut) | full | stream."""
        model = self._load_voxcpm()
        mode = os.getenv("VOX_MODE", "sentence")
        tag = lambda t: "(Tunisian Dialect) " + t
        if mode == "stream":
            for chunk in model.generate_streaming(text=tag(text)):
                yield chunk, self._vox_sr
            return
        parts = [text] if mode == "full" else split_sentences(text)
        for part in parts:
            yield model.generate(text=tag(part)), self._vox_sr

    def _speak_sapi(self, text: str, language: str) -> None:
        import pyttsx3
        engine = pyttsx3.init()
        hint = {"fr": "french", "en": "english", "derja": "arabic"}[language]
        for v in engine.getProperty("voices"):
            if hint in v.name.lower() or hint in str(v.languages).lower():
                engine.setProperty("voice", v.id)
                break
        engine.say(text)
        engine.runAndWait()

    # ---------------- entrée : tu parles ----------------
    def _get_whisper(self, language: str = "fr"):
        name = self.stt_model_name or ("base.en" if language == "en" else "base")
        if name not in self._whisper:
            from faster_whisper import WhisperModel
            print(f"  (chargement du modele de transcription '{name}', 1re fois seulement...)")
            self._whisper[name] = WhisperModel(name, device=self.device, compute_type=self.compute_type)
        return self._whisper[name]

    def transcribe(self, audio, language: str) -> str:
        t = time.time()
        segments, _ = self._get_whisper(language).transcribe(
            audio, language=WHISPER_LANG[language], vad_filter=True,
            beam_size=int(os.getenv("STT_BEAM", "1")), condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segments).strip()
        self.last_stt_s = time.time() - t
        return text

    def record(self):
        """Mode manuel : Entrée pour terminer."""
        import numpy as np, sounddevice as sd
        chunks = []

        def cb(indata, frames, t, status):
            chunks.append(indata.copy())

        with sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=cb):
            input("  [micro actif] parle, puis appuie sur Entree pour terminer... ")
        return np.concatenate(chunks).flatten() if chunks else np.zeros(0, dtype="float32")

    def listen(self, language: str) -> str:
        audio = self.record()
        if len(audio) < SR * 0.5:
            return ""
        return self.transcribe(audio, language)

    def listen_auto(self, language: str, silence_s: float | None = None,
                    start_timeout_s: float = 30.0) -> tuple[str, float | None]:
        """Mode mains libres : attend que tu parles, s'arrête après un silence.
        Retourne (texte, secondes d'attente avant que tu commences à parler) ; ('', None) si silence total."""
        import numpy as np, sounddevice as sd
        block = int(SR * 0.032)
        q: queue.Queue = queue.Queue()
        ep = Endpointer(block_s=block / SR, start_timeout_s=start_timeout_s,
                        silence_s=silence_s or float(os.getenv("VAD_SILENCE", "0.8")))
        ring: collections.deque = collections.deque(maxlen=int(0.6 / ep.block_s))
        chunks: list = []
        speaking, t_start, t0 = False, 0.0, time.time()
        last_print, peak = time.time(), 0.0

        def cb(indata, frames, t, status):
            q.put(indata[:, 0].copy())

        time.sleep(0.3)  # laisse retomber l'écho de la voix du client
        stream = None
        for attempt in range(3):  # certains pilotes Windows refusent de rouvrir le micro du premier coup
            try:
                stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=block, callback=cb)
                stream.start()
                break
            except Exception:
                stream = None
                if attempt == 2:
                    raise
                time.sleep(0.5)
        try:
            while True:
                try:
                    b = q.get(timeout=3.0)
                except queue.Empty:
                    raise RuntimeError("le micro ne fournit aucun son (occupé, débranché ou utilisé par une autre application)")
                rms = float(np.sqrt(np.mean(b * b)))
                peak = max(peak, rms)
                ev = ep.feed(rms)
                (chunks if speaking else ring).append(b)
                if ev == "start":
                    speaking, chunks, t_start = True, list(ring), time.time() - t0
                elif ev == "end":
                    break
                elif ev == "timeout":
                    return "", None
                if not speaking and ep.state == "wait" and time.time() - last_print > 4:
                    print(f"   (j'attends ta voix... niveau micro max {peak:.3f} | seuil {ep.threshold:.3f})")
                    last_print, peak = time.time(), 0.0
        finally:
            if stream is not None:
                stream.stop()
                stream.close()
        text = self.transcribe(np.concatenate(chunks), language)
        return text, max(0.0, t_start - ep.min_speech_s)
