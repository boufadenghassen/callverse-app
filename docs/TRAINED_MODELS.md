# Trained models: the advisor's intent model (used by the advisor and the complaint agent)

## What was trained

| | Advisor intent model |
|---|---|
| Task | What a telecom customer wants: 26 intents (dispute an invoice, poor signal, roaming, cancel the plan...) |
| Model | `sentence-transformers/all-MiniLM-L6-v2` (22 M parameters) fine-tuned, 4 epochs, then exported to **ONNX int8 (23 MB)** |
| Data | [Bitext telco customer support](https://huggingface.co/datasets/bitext/Bitext-telco-llm-chatbot-training-dataset): 25 986 messages after removing duplicates, split 80/10/10 by intent. CDLA-Sharing-1.0, attribution: Bitext |
| Where | Trained on Colab (T4 GPU) with `models/training/1_advisor_intent_model.ipynb` |

| Evaluation | TF-IDF + logistic regression (baseline) | Fine-tuned MiniLM | MiniLM ONNX int8 (shipped) |
|---|---|---|---|
| Bitext test split (2 599 messages, same templates: optimistic) | macro-F1 0.992 | macro-F1 1.000 | macro-F1 1.000 (100% same answers as PyTorch) |
| **30 call-centre sentences written by hand (the honest number)** | **57% (17/30)** | **67% (20/30)** | **73% (22/30)** |

What it still gets wrong (hand-written set): "my internet stopped working this morning" read as *cancel plan*, "my phone was stolen, block my line"
as *cancel plan*, "calls keep dropping at work" as *call services*. Bitext is semi-synthetic (template variations), so real calls are needed to go further.

## How it is used (always on top of the rules, always explained)

**Advisor** (`services/agents/intent_model.py`, `advisor.py`): the model says *what the customer wants*; the facts still come from the knowledge base.
- Retrieval = TF-IDF cosine + `0.3 x confidence` for the passages mapped to the predicted intent (`PASSAGES`), only when the model is sure (>= 0.5).
  "the amount on my statement is wrong" finds *Disputing an invoice* without sharing its words.
- An intent the knowledge base does not cover yet (install internet, poor coverage...) is **named and escalated** instead of answered with a wrong passage.
- `/advisor/suggest` returns `intentModel` (intent, confidence, two alternatives) next to the sources.

**Complaint agent** (`complaints_agent/engine.py`): when no root-cause pattern matches, the intent model reads the complaint
(`INTENT_CLUSTER`), e.g. "my mobile shows no bars at home" -> *Network and service quality*. Each case says who decided: `clusterBy` = `rules`,
`intent model 93% (report poor signal coverage)` or `none`.

## Tested and rejected: escalation and severity models on real complaints

`models/training/2_complaints_models.ipynb` trained TF-IDF + logistic regression on **277 259 real complaints** (US CFPB Consumer Complaint Database):

| Target | ROC-AUC (CFPB test) | On our telecom complaints |
|---|---|---|
| Escalation: will the customer dispute the answer? | 0.64 | **Backwards**: a polite invoice question 0.61, "this is fraud, my lawyer will contact you" 0.34 |
| Severity: will money be paid back? | 0.91 | No signal: every telecom complaint between 0.12 and 0.31 |

The strongest words were US company names (Equifax, Scottrade, Macy's...), not how the customer writes: the models do not transfer from US
financial complaints to telecom. Plugging them in would have made the agent worse, so the complaint agent keeps its explained rules for
severity and escalation. Next step: label our own complaints (the agent's history) and train on those.

## Install and switches

1. `pip install -r services/agents/requirements-models.txt` (onnxruntime + tokenizers, no PyTorch).
2. Unzip `advisor_intent_onnx.zip` into `services/agents/models/advisor_intent_model/` (not in Git) and restart the agents service.
3. `GET /health` shows `trainedModels.advisorIntent` with the scores above when the model is loaded.

`ADVISOR_INTENT_MODEL=0` turns it off; `ADVISOR_INTENT_MODEL=<folder>` points elsewhere. The tests run with it off (`services/agents/conftest.py`);
`tests/test_trained_models.py` checks the wiring with a stand-in and, when the files are present, the real model.
