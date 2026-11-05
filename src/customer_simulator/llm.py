"""Backends LLM interchangeables : ollama (local), anthropic (cloud), mock (tests).
Choix par variables d'environnement, voir .env.example."""
import json
import os
import re
from typing import Protocol


class LLM(Protocol):
    def complete(self, system: str, messages: list[dict], max_tokens: int = 300,
                 json_mode: bool = False) -> str: ...


class OllamaLLM:
    """Modèle local via Ollama. Fonctionne sur GTX 1080 avec un modèle 7-9B quantifié."""

    def __init__(self, model: str = "qwen2.5:7b", url: str | None = None, num_ctx: int | None = None):
        self.model = model
        self.url = url or os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.num_ctx = num_ctx or int(os.getenv("OLLAMA_NUM_CTX", "4096"))

    def _payload(self, system, messages, max_tokens, json_mode, stream):
        payload = {
            "model": self.model, "stream": stream,
            "messages": [{"role": "system", "content": system}, *messages],
            "options": {"num_predict": max_tokens, "num_ctx": self.num_ctx,
                        "temperature": 0.2 if json_mode else 0.7,
                        "repeat_penalty": 1.0 if json_mode else 1.15},
        }
        if json_mode:
            payload["format"] = "json"
        if os.getenv("OLLAMA_NUM_GPU", "") != "":      # 0 = Ollama sur CPU, libère la carte graphique
            payload["options"]["num_gpu"] = int(os.environ["OLLAMA_NUM_GPU"])
        ka = os.getenv("OLLAMA_KEEP_ALIVE", "30m")     # garde le modèle en mémoire (0 = le décharge après chaque réponse)
        if ka:
            payload["keep_alive"] = int(ka) if ka.lstrip("-").isdigit() else ka
        return payload

    def complete(self, system, messages, max_tokens=300, json_mode=False):
        import requests
        r = requests.post(f"{self.url}/api/chat",
                          json=self._payload(system, messages, max_tokens, json_mode, False), timeout=180)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()

    def stream(self, system, messages, max_tokens=300):
        """Rend le texte morceau par morceau, dès qu'Ollama le produit (fermer le générateur coupe la génération)."""
        import requests
        with requests.post(f"{self.url}/api/chat", json=self._payload(system, messages, max_tokens, False, True),
                           stream=True, timeout=180) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                d = json.loads(line)
                piece = d.get("message", {}).get("content", "")
                if piece:
                    yield piece
                if d.get("done"):
                    break


class AnthropicLLM:
    def __init__(self, model: str = "claude-sonnet-5-5"):
        from anthropic import Anthropic
        from dotenv import load_dotenv
        load_dotenv()
        self.client = Anthropic()
        self.model = model

    def complete(self, system, messages, max_tokens=300, json_mode=False):
        r = self.client.messages.create(model=self.model, max_tokens=max_tokens,
                                        system=system, messages=messages)
        return "".join(b.text for b in r.content if b.type == "text").strip()


class MockLLM:
    """Réponses canned par langue : teste la boucle sans modèle ni API."""
    LINES = {
        "fr": ["Bonjour, j'ai un souci avec ma facture.", "Ce n'est pas ce que je demande.", "Je veux parler à un responsable."],
        "en": ["Hi, my internet keeps dropping.", "That doesn't answer my question.", "I want a manager, please."],
        "derja": ["Aslema, 3andi mochkla fil facture.", "Ma fhemtekch, 3awed 9olli.", "Nheb nkallem el responsable."],
    }

    def __init__(self):
        self.n = 0

    def complete(self, system, messages, max_tokens=300, json_mode=False):
        if json_mode:
            last = messages[-1]["content"].lower()
            vague = "veuillez patienter" in last or "please wait" in last
            return json.dumps({"relevance": 0.2 if vague else 0.8, "empathy": 0.5,
                               "repeated_question": False, "resolved": "c'est réglé" in last})
        lang = "derja" if "ARABIZI" in system else ("en" if "natural English" in system else "fr")
        line = self.LINES[lang][min(self.n, 2)]
        self.n += 1
        return line


class HeuristicEvalLLM:
    """Évaluateur SANS modèle (instantané) : mots-clés + recouvrement avec le message du client.
    Moins fin qu'un LLM, mais supprime un appel complet par tour. Usage : EVAL_BACKEND=heuristic."""
    EMPATHY = ("désolé", "desole", "navré", "pardon", "excuse", "je comprends", "vous comprends",
               "merci de votre patience", "sorry", "apologi", "i understand", "thank you for your patience")
    RESOLVED = ("c'est réglé", "est réglé", "est résolu", "résolu", "corrigé", "remboursé", "je vous rembourse",
                "j'ai annulé", "c'est fait", "has been resolved", "fixed", "refunded", "all set")
    VAGUE = ("veuillez patienter", "patientez", "please hold", "one moment", "un instant")
    ACTION = ("je vais", "je vérifie", "je regarde", "je corrige", "je transmets", "nous allons", "i will", "let me")

    def complete(self, system, messages, max_tokens=300, json_mode=False):
        client, _, adv = messages[-1]["content"].partition("\nConseiller :")
        a, c = adv.strip().lower(), client.replace("Client :", "", 1).lower()
        words = lambda t: {w for w in re.findall(r"\w+", t) if len(w) >= 4}
        cw, aw = words(c), words(a)
        relevance = 0.3 + 0.4 * min(1.0, len(cw & aw) / max(1, min(len(cw), 5)))
        relevance += 0.1 * ("?" in a) + 0.1 * any(k in a for k in self.ACTION)
        if len(a.split()) < 5 or any(k in a for k in self.VAGUE):
            relevance = min(relevance, 0.25)
        resolved = any(k in a for k in self.RESOLVED)
        if resolved:
            relevance = max(relevance, 0.8)
        empathy = 0.4 + 0.25 * sum(k in a for k in self.EMPATHY)
        return json.dumps({"relevance": round(min(relevance, 1.0), 2), "empathy": round(min(empathy, 0.95), 2),
                           "repeated_question": False, "resolved": resolved})


def parse_json(text: str) -> dict:
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)


def make_llm(role: str = "LLM") -> LLM:
    """role = 'LLM' (client simulé) ou 'EVAL' (évaluateur). EVAL retombe sur LLM si non défini."""
    from dotenv import load_dotenv
    load_dotenv()
    backend = os.getenv(f"{role}_BACKEND") or os.getenv("LLM_BACKEND", "ollama")
    model = os.getenv(f"{role}_MODEL") or os.getenv("LLM_MODEL")
    if backend == "mock":
        return MockLLM()
    if backend == "heuristic":
        return HeuristicEvalLLM()
    if backend == "ollama":
        return OllamaLLM(model or "qwen2.5:7b")
    if backend == "anthropic":
        return AnthropicLLM(model or "claude-sonnet-5-5")
    raise ValueError(f"Backend inconnu: {backend}")
