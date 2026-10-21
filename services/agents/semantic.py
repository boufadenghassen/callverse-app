"""A semantic second opinion for the quality analyst's detectors.

The keyword rules in quality.py miss paraphrases ("you'll have your money back today" is a promise, but no keyword says so). Here every
sentence the advisor says is embedded with a small sentence-embedding model (all-MiniLM-L6-v2, 22 M parameters, offline, from the normal
Hugging Face cache) and compared with a few prototype sentences per move; a move is detected when the cosine similarity reaches that move's
threshold. The thresholds are tuned on the development calls of quality_eval_cases.py only (see tune()), never on the held-out test calls.
Without the model files the analyst silently falls back to its keyword rules.
"""
import functools
import os

import numpy as np

MODEL_ID = os.environ.get("QUALITY_EMBEDDER", "sentence-transformers/all-MiniLM-L6-v2")

PROTOTYPES = {
    "EMPATHY": ["I'm sorry about that.", "I understand how frustrating this must be.", "That sounds really stressful, I would be upset too.",
                "I apologise for the inconvenience.", "Thank you for your patience.", "I can see why you are upset.",
                "That must be really upsetting, I am sorry.", "I totally get why you are angry.", "I hear you, that is a lot to deal with."],
    "CHECK_POLICY": ["Let me check the policy first.", "I need to verify the rules before I confirm.", "Let me look at what our procedure says.",
                     "I will check the eligibility conditions.", "Let me make sure this is allowed before I promise anything."],
    "PROMISE": ["I will refund you right away.", "You will get your money back today.", "I am crediting the full amount to your account now.",
                "Consider it done, the refund is on its way.", "I will put the money back on your card immediately.",
                "The money is going back to your account now.", "I am reversing the charge right now.", "You can count on getting that amount back today.", "That amount will be back on your card by tonight."],
    "FOLLOW_UP": ["I will send you a confirmation by email with a reference number.", "You will receive a written summary and your ticket number.",
                  "I will call you back to check that everything is fine.", "I will follow up with you tomorrow.",
                "You can expect an email from us tonight.", "I will check on this case myself tomorrow.", "A case number will reach you by text message.", "I will write to you with the details."],
    "ASK_REPEAT": ["Could you explain the problem again from the start?", "Can you tell me the whole story once more?", "Please repeat what happened.",
                "Could you go through it all one more time?", "Remind me what the problem was.", "From the top, what exactly happened?"],
    "TRANSFER": ["Let me transfer you to the billing team.", "I will put you through to another department.", "I will pass you to a colleague who can help.",
                "I will hand you over to someone in billing.", "I am forwarding you to the specialists.", "Your call will be moved to another team."],
    "GREETING": ["Hello, thank you for calling.", "Good morning, how can I help you today?", "Welcome, you are speaking with Karim.",
                "Hey, support here, what can I do for you?", "Good evening, thanks for holding.", "Customer service, how may I assist you?"],
    "CLOSING": ["Is there anything else I can help you with?", "Thank you for calling, have a nice day.", "I am glad I could help.",
                "Is there anything more I can do for you?", "Take care, and thanks for your patience.", "Thanks for calling, have a good day."],
    "GUARANTEE": ["This will never happen again, I guarantee it.", "It is one hundred percent solved.", "You can be completely sure this will not occur again.",
                  "Rest assured, it can never happen again."],
    "IDENTITY": ["Can you confirm your date of birth so I can verify your identity?", "I need to make sure who I am speaking with.",
                 "Please confirm your full name and address.",
                "Before I start, I need your full name and the address on file.", "For security I need to confirm who you are first."],
}
THRESHOLDS = {move: 0.60 for move in PROTOTYPES}
THRESHOLDS.update(CHECK_POLICY=0.45, FOLLOW_UP=0.55, TRANSFER=0.70)          # tuned on the DEVELOPMENT calls by quality_eval.tune(); the rest kept the default 0.60

_model = None
_protos: dict[str, np.ndarray] | None = None


def available() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache(MODEL_ID, "config.json"), str)
    except Exception:
        return False


def _embed(texts: list[str]) -> np.ndarray:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_ID, device="cpu", local_files_only=True)
    return np.asarray(_model.encode(texts, normalize_embeddings=True, show_progress_bar=False), dtype="float32")


@functools.lru_cache(maxsize=8192)
def scores(sentence: str) -> dict[str, float]:
    """Highest cosine similarity of the sentence to each move's prototypes."""
    global _protos
    if _protos is None:
        _protos = {m: _embed(p) for m, p in PROTOTYPES.items()}
    v = _embed([sentence])[0]
    return {m: float((p @ v).max()) for m, p in _protos.items()}


def flags(sentence: str) -> set[str]:
    return {m for m, s in scores(sentence).items() if s >= THRESHOLDS[m]}
