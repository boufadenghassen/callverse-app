"""Customer Simulator Agent : profil -> message -> évaluation Advisor -> émotion."""
import os
import time
from difflib import SequenceMatcher
from .schemas import Scenario, Profile, EmotionState, CustomerMessage, AdvisorSignals
from .generator import generate_profile, load_intents
from .emotion import update_emotion, decide_action, mood_label
from .prompts import build_system_prompt, EVAL_SYSTEM
from .llm import LLM, parse_json

CLOSINGS = {
    "fr": {"resolved": "Merci, c'est réglé.", "escalate": "Je veux parler à un responsable.", "hangup": "Laissez tomber."},
    "en": {"resolved": "Thanks, that's sorted.", "escalate": "I want to speak to a manager.", "hangup": "Forget it."},
    "derja": {"resolved": "Yaatik essaha, tawa behi.", "escalate": "Nheb nkallem el responsable.", "hangup": "Khalliha, bye."},
}


class ReplyStream:
    """Réplique du client en cours de génération.
      pieces()   : morceaux de texte au fil de l'eau (à jouer / afficher)
      finish(s)  : clôt le tour. `spoken` = ce qui a réellement été dit (si le client a été coupé).
      close()    : arrête la génération."""

    def __init__(self, agent, source, signals, action):
        self.agent, self.source, self.signals, self.action = agent, source, signals, action
        self.t0 = time.time()
        self.first_piece_s = None
        self.buf: list[str] = []

    def pieces(self):
        for piece in self.source:
            if self.first_piece_s is None:
                self.first_piece_s = time.time() - self.t0
            self.buf.append(piece)
            yield piece

    def close(self) -> None:
        try:
            self.source.close()
        except Exception:
            pass  # déjà terminé, ou encore en cours dans un autre thread

    def finish(self, spoken: str | None = None) -> CustomerMessage:
        self.close()
        return self.agent._finish_stream(self, spoken if spoken is not None else "".join(self.buf))


class CustomerSimulatorAgent:
    def __init__(self, llm: LLM, eval_llm: LLM | None = None):
        self.llm = llm
        self.eval_llm = eval_llm or llm
        self.intents_desc = load_intents()
        self.profile: Profile | None = None
        self.emotion: EmotionState | None = None
        self.scenario: Scenario | None = None
        self.history: list[dict] = []
        self.turn = 0
        self.revealed_hidden = False
        self.timings: dict[str, float] = {}
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "140"))

    # --- API publique -------------------------------------------------
    def start(self, scenario: Scenario) -> CustomerMessage:
        self.scenario = scenario
        self.profile, self.emotion = generate_profile(scenario)
        self.history, self.turn, self.revealed_hidden = [], 0, False
        return self._speak("(Le conseiller décroche. Dis ton premier message.)")

    def reply(self, advisor_text: str, wait_seconds: float = 0.0) -> CustomerMessage:
        assert self.profile and self.emotion and self.scenario, "appelle start() d'abord"
        self.timings = {}
        t = time.time()
        signals = self.evaluate_advisor(advisor_text)
        self.timings["eval"] = time.time() - t
        self._penalize_repeat(signals, advisor_text)
        signals.wait_seconds = wait_seconds
        self.emotion = update_emotion(self.emotion, signals, self.scenario.difficulty)
        action = decide_action(self.emotion, signals.resolved)
        if action != "continue":
            return self._final(advisor_text, action, signals)
        if self.turn >= self.scenario.max_turns:
            return self._final(advisor_text, "hangup", signals)
        if self.emotion.trust > 0.6 and self.turn >= 2:
            self.revealed_hidden = True
        return self._speak(advisor_text, signals)

    # --- réponse en flux (la voix démarre pendant que le LLM écrit) ----
    def start_stream(self, scenario: Scenario) -> "ReplyStream":
        self.scenario = scenario
        self.profile, self.emotion = generate_profile(scenario)
        self.history, self.turn, self.revealed_hidden = [], 0, False
        self.timings = {}
        return self._open_stream("(Le conseiller décroche. Dis ton premier message.)", None)

    def reply_stream(self, advisor_text: str, wait_seconds: float = 0.0, interrupted: bool = False) -> "ReplyStream":
        assert self.profile and self.emotion and self.scenario, "appelle start_stream() d'abord"
        self.timings = {}
        t = time.time()
        signals = self.evaluate_advisor(advisor_text)
        self.timings["eval"] = time.time() - t
        self._penalize_repeat(signals, advisor_text)
        signals.wait_seconds = wait_seconds
        self.emotion = update_emotion(self.emotion, signals, self.scenario.difficulty)
        if interrupted:  # être coupé la parole énerve un peu
            self.emotion.frustration = min(1.0, self.emotion.frustration + 0.05)
        action = decide_action(self.emotion, signals.resolved)
        if action == "continue" and self.turn >= self.scenario.max_turns:
            action = "hangup"
        if action != "continue":
            self.history.append({"role": "user", "content": advisor_text})
            text = self._closing_line(advisor_text, action)
            return ReplyStream(self, iter([text]), signals, action)
        if self.emotion.trust > 0.6 and self.turn >= 2:
            self.revealed_hidden = True
        note = "(Le conseiller vient de te couper la parole.) " if interrupted else ""
        return self._open_stream(note + advisor_text, signals)

    def _open_stream(self, advisor_text: str, signals) -> "ReplyStream":
        system = build_system_prompt(self.profile, self.emotion, self.intents_desc, self.revealed_hidden)
        self.history.append({"role": "user", "content": advisor_text})
        stream = getattr(self.llm, "stream", None)
        if stream:
            source = stream(system, self._window(), self.max_tokens)
        else:  # backend sans flux (mock, cloud) : une seule "tranche"
            source = iter([self.llm.complete(system, self._window(), self.max_tokens)])
        return ReplyStream(self, source, signals, "continue")

    def _finish_stream(self, rs: "ReplyStream", text: str) -> CustomerMessage:
        text = text.strip() or "…"
        self.history.append({"role": "assistant", "content": text})
        self.turn += 1
        self.timings["gen"] = time.time() - rs.t0
        if rs.first_piece_s is not None:
            self.timings["first"] = rs.first_piece_s
        return self._build(text, rs.action, rs.signals)

    # --- interne ------------------------------------------------------
    def _penalize_repeat(self, signals: AdvisorSignals, advisor_text: str) -> None:
        # l'Advisor se répète mot pour mot : pénalité quel que soit l'avis de l'évaluateur
        prev = [m["content"] for m in self.history if m["role"] == "user"]
        if prev and advisor_text.strip().lower() == prev[-1].strip().lower():
            signals.relevance = min(signals.relevance, 0.15)
            signals.repeated_question = True
            signals.resolved = False

    def evaluate_advisor(self, advisor_text: str) -> AdvisorSignals:
        last_client = next((m["content"] for m in reversed(self.history) if m["role"] == "assistant"), "")
        prompt = f"Client : {last_client}\nConseiller : {advisor_text}"
        try:
            raw = self.eval_llm.complete(EVAL_SYSTEM, [{"role": "user", "content": prompt}], 150, json_mode=True)
            data = parse_json(raw)
            return AdvisorSignals(**{k: data[k] for k in ("relevance", "empathy", "repeated_question", "resolved") if k in data})
        except Exception:
            return AdvisorSignals()  # neutre si l'évaluation échoue

    def _window(self) -> list[dict]:
        """Derniers messages (contexte limité des petits modèles), en commençant par un tour 'user'."""
        msgs = self.history[-12:]
        while msgs and msgs[0]["role"] != "user":
            msgs = msgs[1:]
        return msgs

    def _too_similar(self, text: str) -> bool:
        prev = [m["content"] for m in self.history if m["role"] == "assistant"]
        return any(SequenceMatcher(None, text.lower(), q.lower()).ratio() > 0.8 for q in prev)

    def _speak(self, advisor_text: str, signals: AdvisorSignals | None = None) -> CustomerMessage:
        system = build_system_prompt(self.profile, self.emotion, self.intents_desc, self.revealed_hidden)
        self.history.append({"role": "user", "content": advisor_text})
        t = time.time()
        text = self.llm.complete(system, self._window(), self.max_tokens)
        if self._too_similar(text):
            # le modèle se répète : une relance avec consigne, puis on garde le meilleur essai
            nudge = self._window()[:-1] + [{"role": "user", "content":
                advisor_text + "\n(Consigne cachée : tu as déjà dit cela. Ne répète pas : réponds à ce que "
                "le conseiller vient de dire, avec des mots différents et une information nouvelle.)"}]
            retry = self.llm.complete(system, nudge, self.max_tokens)
            if retry and not self._too_similar(retry):
                text = retry
        self.timings["gen"] = time.time() - t
        self.history.append({"role": "assistant", "content": text})
        self.turn += 1
        return self._build(text, "continue", signals)

    def _final(self, advisor_text: str, action: str, signals: AdvisorSignals) -> CustomerMessage:
        self.history.append({"role": "user", "content": advisor_text})
        self.turn += 1
        t = time.time()
        text = self._closing_line(advisor_text, action)
        self.timings["gen"] = time.time() - t
        self.history.append({"role": "assistant", "content": text})
        return self._build(text, action, signals)

    def _closing_line(self, advisor_text: str, action: str) -> str:
        fallback = CLOSINGS[self.profile.language][action]
        instr = {
            "resolved": "Ton problème est réglé : remercie brièvement et conclus.",
            "escalate": "Tu n'en peux plus : exige de parler à un responsable.",
            "hangup": "Tu as perdu patience : dis une dernière phrase sèche puis raccroche.",
        }[action]
        system = build_system_prompt(self.profile, self.emotion, self.intents_desc, self.revealed_hidden)
        msgs = self._window()[:-1] + [{"role": "user",
                                     "content": f"{advisor_text}\n(Consigne cachée : {instr} Une seule phrase courte, dans ta langue.)"}]
        try:
            out = self.llm.complete(system, msgs, 80).strip()
            return out or fallback
        except Exception:
            return fallback

    def _build(self, text: str, action: str, signals: AdvisorSignals | None) -> CustomerMessage:
        return CustomerMessage(
            text=text, emotion=self.emotion.model_copy(), action=action, turn=self.turn,
            metadata={
                "persona_id": self.profile.persona_id, "language": self.profile.language,
                "intents": self.profile.intents, "hidden_intent": self.profile.hidden_intent,
                "hidden_revealed": self.revealed_hidden, "mood": mood_label(self.emotion),
                "last_advisor_signals": signals.model_dump() if signals else None,
            },
        )
