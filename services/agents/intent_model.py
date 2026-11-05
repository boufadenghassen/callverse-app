"""The advisor's trained intent model: what a telecom customer wants, read with a fine-tuned MiniLM.

TF-IDF (advisor.py) only matches words, so "my bill is wrong" and "dispute an invoice" look unrelated to it. This model was fine-tuned on the
Bitext telco customer-support dataset (26 intents, ~26,000 messages, CDLA-Sharing-1.0) in models/training/1_advisor_intent_model.ipynb, and it
understands paraphrases. It only says WHAT the customer wants: the facts still come from the knowledge base and its sources.

The model is exported to ONNX int8 (~25 MB, same answers as the PyTorch model on the test split) and runs with onnxruntime and tokenizers
(requirements-models.txt); the full PyTorch folder works too when torch and transformers are installed. The files are not in Git: unzip
`advisor_intent_onnx.zip` into services/agents/models/advisor_intent_model/, or point ADVISOR_INTENT_MODEL at the folder. Without them `predict`
answers None and the advisor keeps its TF-IDF behaviour. ADVISOR_INTENT_MODEL=0 switches the model off.
"""
import functools
import json
import os
from pathlib import Path

DEFAULT_DIR = Path(__file__).parent / "models" / "advisor_intent_model"
MIN_CONFIDENCE = 0.5     # under this the model is not sure: the advisor does not lean on it

# what each intent the model knows points to in OUR knowledge base (titles of knowledge/base.json); [] = no passage covers it yet
PASSAGES = {
    "dispute_invoice": ["Disputing an invoice", "Duplicate charge on a bill"],
    "invoices": ["Disputing an invoice"],
    "get_compensation": ["How a refund is approved", "Compensation for a failed roaming bundle"],
    "check_excess_data_charges": ["Data limit does not match the plan"],
    "check_usage": ["Data limit does not match the plan"],
    "set_usage_limits": ["Data limit does not match the plan"],
    "customer_service": ["Transfers and callbacks"],
    "human_agent": ["Transfers and callbacks"],
    "check_mobile_payments": ["Payment methods and late payment"],
    "payment_methods": ["Payment methods and late payment"],
    "pay": ["Payment methods and late payment"],
    "schedule_payments": ["Payment methods and late payment"],
    "activate_roaming": ["Roaming bundle not working abroad"],
    "activate_phone": ["SIM card replacement"],
    "deactivate_phone": ["SIM card replacement"],
    "cancel_plan": ["Cancellation and early termination fee"],
    "check_cancellation_fee": ["Cancellation and early termination fee"],
    "change_provider": ["Cancellation and early termination fee"],
    "change_plan": ["Changing the plan"],
    "sign_up_for_plan": ["Changing the plan"],
    "report_poor_signal_coverage": [], "report_problem": [], "check_signal_coverage": [], "install_internet": [],
    "activate_call_management_services": [], "deactivate_call_management_services": [],
}
# the advisor's intent chips (advisor.INTENT_WORDS) for each model category
CHIPS = {"BILLING": "Billing", "PAYMENT": "Billing", "SUBSCRIPTION": "Plan change", "CONSUMPTION": "Data usage", "COMPLAINTS": "Complaint"}


def model_dir() -> Path | None:
    setting = os.environ.get("ADVISOR_INTENT_MODEL")
    if setting == "0":
        return None
    path = Path(setting) if setting else DEFAULT_DIR
    return path if (path / "config.json").exists() else None


@functools.lru_cache(maxsize=1)
def _load():
    """(run, labels, meta): run(text) gives the probabilities. ONNX int8 (onnxruntime + tokenizers, ~25 MB) first, else PyTorch."""
    path = model_dir()
    if path is None:
        return None
    meta = json.loads((path / "metrics.json").read_text(encoding="utf-8")) if (path / "metrics.json").exists() else {}
    config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    labels = {int(k): v for k, v in config["id2label"].items()}
    max_len = int(meta.get("max_len", 64))
    if (path / "model.onnx").exists():
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError:
            pass
        else:
            session = ort.InferenceSession(str(path / "model.onnx"), providers=["CPUExecutionProvider"])
            tok = Tokenizer.from_file(str(path / "tokenizer.json"))
            tok.enable_truncation(max_len)
            tok.no_padding()

            def run(text: str) -> list[float]:
                enc = tok.encode(text)
                feed = {"input_ids": np.array([enc.ids], dtype=np.int64), "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
                        "token_type_ids": np.array([enc.type_ids], dtype=np.int64)}
                logits = session.run(None, feed)[0][0]
                e = np.exp(logits - logits.max())
                return (e / e.sum()).tolist()
            return run, labels, meta
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError:
        return None
    tok = AutoTokenizer.from_pretrained(path)
    model = AutoModelForSequenceClassification.from_pretrained(path).eval()

    def run(text: str) -> list[float]:
        with torch.no_grad():
            return torch.softmax(model(**tok([text], truncation=True, max_length=max_len, return_tensors="pt")).logits, -1)[0].tolist()
    return run, labels, meta


def available() -> bool:
    return _load() is not None


def info() -> dict | None:
    """What the model is and how well it did on its evaluation (for the health page and the validation)."""
    loaded = _load()
    if loaded is None:
        return None
    meta = loaded[2]
    keep = ("model", "test_accuracy", "test_macro_f1", "hand_written_accuracy", "hand_written_examples", "baseline_tfidf", "onnx_int8", "data")
    return {k: meta[k] for k in keep if k in meta}


@functools.lru_cache(maxsize=512)
def predict(text: str) -> dict | None:
    """{intent, label, category, chip, confidence, sure, alternatives, passages} for the customer's words, or None without the model."""
    loaded = _load()
    if loaded is None or not text.strip():
        return None
    run, labels, meta = loaded
    probs = run(text)
    ranked = sorted(range(len(probs)), key=lambda i: -probs[i])
    best = labels[ranked[0]]
    category = meta.get("intent_category", {}).get(best)
    return dict(intent=best, label=best.replace("_", " "), category=category, chip=CHIPS.get(category or ""),
                confidence=round(probs[ranked[0]], 3), sure=probs[ranked[0]] >= MIN_CONFIDENCE,
                alternatives=[dict(intent=labels[i], confidence=round(probs[i], 3)) for i in ranked[1:3]],
                passages=PASSAGES.get(best, []))
