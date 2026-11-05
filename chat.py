"""Appel vocal : TOI = le conseiller, l'IA = le client (français ou anglais). 100 % local.

  python chat.py                          client aléatoire (fr/en), mains libres
  python chat.py --barge-in               + tu peux couper la parole au client (CASQUE obligatoire)
  python chat.py --lang en --gender F     cliente anglophone
  python chat.py --persona fr_m --difficulty 4
  python chat.py --manual                 micro avec Entrée (parler / terminer)
  python chat.py --text                   clavier seulement
Pour arrêter : dis « stop simulation », ou Ctrl+C.
"""
import argparse, json, os, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "src")
ap = argparse.ArgumentParser(description="Customer Simulator Agent - appel vocal local")
ap.add_argument("--persona", help="fr_f, fr_m, en_f, en_m (sinon tiré au hasard)")
ap.add_argument("--lang", choices=["fr", "en"])
ap.add_argument("--gender", choices=["F", "M"])
ap.add_argument("--difficulty", type=int, default=3, help="1 (facile) à 5 (très dur)")
ap.add_argument("--seed", type=int, help="même graine = même client")
ap.add_argument("--text", action="store_true", help="clavier seulement, sans voix")
ap.add_argument("--manual", action="store_true", help="micro avec Entrée au lieu du mains libres")
ap.add_argument("--barge-in", action="store_true", help="coupure de parole (écoute pendant que le client parle) : casque !")
ap.add_argument("--smart-eval", action="store_true", help="note tes réponses avec le LLM (plus fin, plus lent)")
ap.add_argument("--hide-emotion", action="store_true", help="cache l'état émotionnel du client")
ap.add_argument("--backend", choices=["ollama", "anthropic", "mock"])
ap.add_argument("--model", help="ex: qwen2.5:7b")
ap.add_argument("--stt-model", help="transcription : base (rapide, défaut) ou small (plus précis, plus lent)")
ap.add_argument("--tts", choices=["local", "edge", "sapi", "voxcpm"],
                help="local (défaut, hors-ligne), edge (en ligne), sapi (Windows), voxcpm (derja)")
ap.add_argument("--fast", action="store_true", help=argparse.SUPPRESS)
a = ap.parse_args()

if a.backend:
    os.environ["LLM_BACKEND"] = a.backend
if a.model:
    os.environ["LLM_MODEL"] = a.model
os.environ.setdefault("LLM_MAX_TOKENS", "120")
if not a.smart_eval:
    os.environ["EVAL_BACKEND"] = "heuristic"   # évaluation instantanée : 1 seul appel LLM par tour
    os.environ.pop("EVAL_MODEL", None)

from customer_simulator import CustomerSimulatorAgent, Scenario, make_llm
from customer_simulator.emotion import mood_label
from customer_simulator.live import iter_sentences
from customer_simulator.llm import MockLLM

llm, eval_llm = make_llm("LLM"), make_llm("EVAL")
agent = CustomerSimulatorAgent(llm, eval_llm)
if not isinstance(llm, MockLLM):
    print("Chargement du modèle de texte...")
    try:
        llm.complete("Réponds par un mot.", [{"role": "user", "content": "ok"}], 5)
    except Exception as ex:
        print(f"  (préchauffage impossible : {ex})")

rs = agent.start_stream(Scenario(persona_id=a.persona, language=a.lang, gender=a.gender,
                                 difficulty=a.difficulty, seed=a.seed))
p = agent.profile

voice = None
if not a.text:
    try:
        from customer_simulator.voice import Voice, make_arabic_converter
        voice = Voice(tts=a.tts, stt_model=a.stt_model, arabic_converter=make_arabic_converter(llm))
        print("Préchauffage de la transcription et de la voix...")
        voice.warmup(p.language, p.persona_id)
    except Exception as ex:
        print(f"  [voix indisponible : {ex}]\n  -> mode clavier (installe requirements-voice.txt pour la voix)")
        voice = None
auto = voice is not None and not a.manual

listener = None
if a.barge_in and auto:
    try:
        from customer_simulator.live import DuplexListener
        listener = DuplexListener()
        listener.open()
        print("Coupure de parole activée : tu peux parler pendant que le client parle (casque conseillé).")
    except Exception as ex:
        print(f"  [coupure de parole indisponible : {ex}] -> écoute classique")
        listener = None
elif a.barge_in:
    print("  (--barge-in demande le mode mains libres : ignoré)")

lang_hint = {"fr": "Parle en français.", "en": "Speak English."}.get(p.language, "")
print(f"\n=== Appel entrant : {p.name}, {p.age} ans ({p.language}) === {lang_hint}")
print("Tu es le conseiller. Dis « stop simulation » (ou Ctrl+C) pour arrêter.\n")

log = {"profile": p.model_dump(), "scenario": agent.scenario.model_dump(), "turns": []}
STOP = {"/quit", "stop simulation", "quitter la simulation", "fin de la simulation"}
silent_total = 0.0


def play_reply(rs):
    """Joue (ou affiche) la réplique du client au fil de sa génération. -> (message, coupé par toi ?)"""
    first = [True]

    def show(sentence):
        print(("[Client] " if first[0] else "         ") + sentence, flush=True)
        first[0] = False

    if not a.hide_emotion:
        e = agent.emotion
        print(f"   (patience={e.patience:.2f} frustration={e.frustration:.2f} "
              f"confiance={e.trust:.2f} | {mood_label(e)})")
    interrupted, spoken, voice_error = False, None, None
    if listener:
        listener.begin_playback()
    if voice and voice.tts != "off":
        try:
            stop = (lambda: listener.barged.is_set()) if listener else None
            interrupted, played = voice.speak_stream(
                iter_sentences(rs.pieces()), p.language, p.gender, p.persona_id, agent.emotion,
                should_stop=stop, on_sentence=show)
            spoken = " ".join(played) if interrupted else None
        except Exception as ex:
            voice_error = ex
    else:
        for s in iter_sentences(rs.pieces()):
            show(s)
    if listener:
        listener.end_playback()
    if voice_error:
        print(f"   [voix indisponible : {voice_error}]")
        list(rs.pieces())
        print("[Client] " + "".join(rs.buf).strip())
    msg = rs.finish(spoken)
    if interrupted:
        print("   (tu as coupé la parole au client)")
    log["turns"].append({"role": "client", "text": msg.text, "emotion": msg.emotion.model_dump(),
                         "action": msg.action, "interrupted": interrupted, "ts": time.time()})
    tm = agent.timings
    extra = f" | premier son {voice.last_first_audio_s:.1f}s" if voice and voice.tts not in ("off",) else ""
    print(f"   [temps] evaluation {tm.get('eval', 0):.1f}s | 1er mot du LLM {tm.get('first', 0):.1f}s{extra}")
    return msg, interrupted


def ask_advisor() -> tuple[str, float]:
    """Retourne (texte, secondes pendant lesquelles le client a attendu avant que tu parles)."""
    global silent_total, auto, listener
    while True:
        try:
            if auto:
                print("[Toi] ... j'ecoute")
                if listener:
                    audio, waited = listener.wait_utterance()
                    s = voice.transcribe(audio, p.language) if audio is not None else ""
                else:
                    s, waited = voice.listen_auto(p.language)
                if not s:
                    if waited is None:
                        silent_total += 30.0
                        print("   (silence)")
                    else:
                        print("   (rien compris)")
                    if listener:  # un nouveau tour d'écoute commence
                        listener.begin_playback()
                        listener.end_playback()
                    continue
                print(f"[Toi, transcrit] {s}  (transcription {voice.last_stt_s:.1f}s)")
                wait, silent_total = (waited or 0.0) + silent_total, 0.0
                return ("/quit" if s.lower().strip(" .!?") in STOP else s), wait
            if voice:
                s = input("[Toi] Entree = parler, ou tape ton message > ").strip()
                if not s:
                    s = voice.listen(p.language)
                    if not s:
                        print("   (rien entendu, recommence)")
                        continue
                    print(f"[Toi, transcrit] {s}")
            else:
                s = input("[Toi] > ").strip()
        except RuntimeError as ex:
            print(f"   [micro] {ex}\n   -> mode Entree : appuie sur Entree pour parler, ou tape ton message")
            auto = False
            if listener:
                listener.close()
                listener = None
            continue
        except (EOFError, KeyboardInterrupt):
            return "/quit", 0.0
        if s:
            return s, 0.0


msg, interrupted = play_reply(rs)
while msg.action == "continue":
    adv, wait = ask_advisor()
    if adv.lower() == "/quit":
        log["outcome"] = "quit"
        break
    log["turns"].append({"role": "advisor", "text": adv, "wait_s": round(wait, 1), "ts": time.time()})
    rs = agent.reply_stream(adv, wait_seconds=wait, interrupted=interrupted)
    msg, interrupted = play_reply(rs)
else:
    log["outcome"] = msg.action
    labels = {"resolved": "Problème résolu", "escalate": "Le client exige un responsable",
              "hangup": "Le client a raccroché"}
    print(f"\n=== Fin d'appel : {labels[msg.action]} ===")

if listener:
    listener.close()
out = Path("transcripts")
out.mkdir(exist_ok=True)
f = out / f"session_{datetime.now():%Y%m%d_%H%M%S}.json"
f.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Transcript enregistré : {f}")
