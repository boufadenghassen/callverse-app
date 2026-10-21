# Quality analyst

Owner: Ghassen. Everything about this agent lives in this folder; the rest of `services/agents` only imports it (`main.py` routes, `from quality_analyst import ...`).

## What it does
It scores a call on five criteria (accuracy, compliance, communication, resolution, customer sentiment) with 18 explainable rules. Every rule finds a moment (turn and time), costs points in one criterion and carries the fix that would have avoided it, so the counterfactual ("if the policy had been checked first, compliance rises from 0 to 3, overall +8") is computed by really removing the finding. The knowledge base (`advisor.py`) is used to check the facts the advisor states and that the problem was answered from it. Rule based, not an LLM judge: an LLM would replace the detectors in `engine.find_issues`, not the structure.

## Files
| File | Role |
|---|---|
| `engine.py` | Rules, scoring, counterfactual, coaching, `rescore` after reviewer verdicts, `review()` |
| `semantic.py` | Second opinion on paraphrases: sentence embeddings (all-MiniLM-L6-v2, offline, from the Hugging Face cache) |
| `store.py` | SQLite call store (`../data/quality.db`, git-ignored, `QUALITY_DB` to move it), reviewer feedback, analytics |
| `seed.py` | Fills an empty store with 84 simulated calls from six advisors, each scored by the real engine |
| `audio.py` | Two-channel recording (advisor left, customer right) to a scored review: cut at silences, Whisper per segment, emotion model for the customer's mood |
| `evaluation.py`, `eval_cases*.py` | Measured accuracy on 213 hand-labelled calls (122 development, 91 held-out test) |
| `labelling/` | Human-agreement study: blind labelling sheet and the script that scores it (see its README) |
| `tests/` | The agent's tests |
| `requirements.txt` | Optional: `sentence-transformers` for the semantic opinion |

## Endpoints (in `../main.py`)
`POST /quality/review`, `/quality/review-call`, `/quality/review-audio`, `/quality/feedback`; `GET /quality/reviews`, `/quality/reviews/{id}`, `/quality/analytics`, `/quality/evaluation`, `/quality/sample-call.wav`. The web app side: `app/src/pages/quality.controller.ts`, `app/views/quality.njk`.

## Three ways in
A transcript through the API; a live call from the advisor console (`review-call`); a two-channel recording (`review-audio`, needs Whisper, and `models/src/serve.py` on port 8001 for the customer's mood, otherwise a word list is used).

## Analytics and feedback
Analytics (averages, 8-week trend, most frequent errors, root causes, a coaching plan per advisor with a training scenario) are computed from the store, not typed in. A reviewer marks a finding Correct or Not an error; a disputed finding stops counting, scores and counterfactual are recomputed, and the team view shows the agreement rate. Reviews can be filtered by advisor, error and score.

## Accuracy
Measured by `evaluation.py` (`GET /quality/evaluation`, shown on the Quality page). First measure on never-seen hard calls: F1 75 % (keywords) / 81 % (with the semantic opinion). After general improvements, on 91 held-out test calls: precision 98 %, recall 100 %, F1 99 % (keywords alone 98 %); development 98 %. Tests keep these above 95 %. The labels are ours and the calls short: a rough score, not a guarantee.
Never tune thresholds or phrase lists on the test split. `QUALITY_EVAL_FINAL=0` hides the final batch while developing.

## Switches and commands
* `QUALITY_SEMANTIC=0` turns the semantic opinion off (it is also off when the model is not cached, as in CI).
* `QUALITY_EMBEDDER`, `EMOTION_URL`, `QUALITY_DB` change the model, the emotion service and the database.
* Tests, from `services/agents`: `pytest -q quality_analyst/tests`
* Accuracy report: `python -m quality_analyst.evaluation`
* To start again from the clean simulated history: delete `../data/quality.db` and restart the agents.
