# orqestra agents service (Python, FastAPI)

The real agents behind the web app's `AgentGateway`. Built so far:

| Agent | Endpoints | How it works |
|---|---|---|
| **Customer simulator** | `POST /customer/sessions`, `POST /customer/sessions/{id}/say` | A persona with mood and patience. It reads what the advisor typed (`read_advisor`), updates mood, patience and churn by fixed rules, and answers (`customer_line`). A port of the web app's training simulator: `tests/test_agents.py` replays recorded calls from the TypeScript version and checks that every turn is identical. No LLM yet; swap `read_advisor` and `customer_line` in `customer.py` and keep their signatures. |
| **Customer advisor** | `POST /advisor/suggest` | TF-IDF retrieval over the demo knowledge base `knowledge/base.json`. Returns the answer, its sources, the match score, detected intents, and a policy warning (refund above 50 TND needs a supervisor). Says so when nothing matches. The confidence is the cosine similarity of the best passage, not a probability. |
| **Voice** | `POST /voice/speak` | Neural text to speech ([Kokoro](https://github.com/thewh1teagle/kokoro-onnx), Apache 2.0, offline on the CPU). The advisor has one voice, each customer persona has her own, and an upset customer speaks faster (speed only: Kokoro does not act out emotions). About one second of compute per second of speech; the web app reads sentence by sentence so the first words start early. |
| **Workforce manager** | `GET /workforce/forecast`, `POST /workforce/simulate` | Forecast = same hour over 8 past weeks plus an intraday correction. Staffing = the Erlang C queueing formula (checked against the textbook value in the tests): average wait and the share of calls answered in 20 s for each hour, with and without extra advisors, and ranked recommendations (add advisors, move one from a queue with spare capacity, offer a callback). The reply lists every hour so the manager can check it. **The call history is synthetic** (no real logs yet): `load_history()` in `workforce.py` is the one place to plug the real data in. |
| **Workforce routing** | `GET /workforce/routing` | Which advisor should work which queue for the rest of the day (`routing.py`). A local search on the Erlang C numbers: for each coming hour it starts from today's roster and repeatedly makes the one move of a cross-skilled advisor that wins the most priority-weighted calls answered within 20 s (queue B, the premium queue, counts 30 % more), never pushing a donor queue below 65 %. Each move is explained by the service levels before and after. A discrete-event simulation (Poisson calls, exponential handling) checks the result independently of the formula; the tests require both to agree. **This is not reinforcement learning**: RL needs real call logs and a calibrated simulator, and would be judged against this baseline. Advisors, skills, priorities and today's call volumes are synthetic. |
| **Workforce breaks and shifts** | `GET /workforce/schedule` | Lunch plan for a typical day (`scheduling.py`). With 20 % more people on shift than desks needed ("shrinkage"), everyone on shift 6 hours or more takes one hour of lunch starting 11h to 14h. Naive plan: all at noon, which leaves that hour at 0 % in every queue. Planned: lunches placed one at a time at the hour that loses the fewest calls answered in 20 s (Erlang C), then polished by local search; a penalty proportional to the calls stops the search from sacrificing a whole hour. What is still short of the 80 % target becomes an overtime estimate. Synthetic advisors and shifts. |
| **Quality analyst** | `POST /quality/review`, `/quality/review-call`, `/quality/review-audio`, `GET /quality/reviews`, `/quality/reviews/{id}`, `/quality/analytics`, `/quality/sample-call.wav` | Scores a call transcript out of 100 on five criteria (accuracy, compliance, communication, resolution, customer sentiment) with 18 explainable rules (`quality.py`). Every rule finds a moment (turn and time), costs points in one criterion and carries the fix that would have avoided it, so the counterfactual ("if the policy had been checked first, compliance rises from 0 to 3, overall +8") is computed by really removing the finding. The knowledge base is used to check the facts the advisor states (dispute delay, plan change timing, refund timing...) and to check that the problem was answered from it. Three ways in: a transcript through the API, a live call of the advisor console (`review-call`), and a **two-channel recording** (advisor left, customer right): each channel is cut at the silences and written down by Whisper, the customer's sentences go through the emotion model (`models/src/serve.py`) for her mood, and the call is scored (`quality_audio.py`). Reviews are kept in SQLite (`data/quality.db`, git-ignored); an empty store is filled with 84 simulated calls from six advisors with different habits, each scored by the real engine, so the **analytics** (averages, 8-week trend, most frequent errors, root causes, a coaching plan per advisor with a training scenario) are computed, not typed in. Rule based, not an LLM judge: an LLM would replace the detectors in `find_issues`, not the structure. |

The other agents (complaints, training, sales) still use demo data in the web app. `HttpAgentGateway` starts
from the demo data and replaces only what exists here, so `AGENTS_MODE=http` already works.

## Run (from this folder)

```
../../../venv/Scripts/python.exe -m uvicorn main:app --port 8000
```

Then start the web app with `AGENTS_MODE=http` (and `CALLVERSE_AGENTS_URL` if the port differs). Open the **Advisor console** as `karim`,
section "Live call with a simulated customer".

## Neural voice: one-time download

The voice needs a package and two model files (about 355 MB, not in git):

```
../../../venv/Scripts/python.exe -m pip install kokoro-onnx
```

Then put `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the [kokoro-onnx model-files-v1.0 release](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0)
into `models/voices/`. Without them the service still runs, `/voice/speak` answers 503 and the web app uses the browser's voices.

## Test

```
../../../venv/Scripts/python.exe -m pytest -q
```

`tests/golden_customer.json` was produced from the compiled TypeScript simulator; regenerate it if the rules in
`app/src/pages/client-simulator.ts` or `customer-llm.ts` change (and change `customer.py` the same way).

## Limits

Live calls are kept in memory (200 at most): restarting the service ends open calls. The knowledge base is invented demo content
for a fictional operator, to be replaced by the real FAQ.

### Voice notes (advisor live call)

The advisor can record a voice note or type. A voice note is turned into a 16 kHz WAV in the page, sent to `POST /voice/transcribe` (Whisper base.en,
GPU, offline), and the text goes to the customer agent; the note stays playable in the call. Typed replies are said aloud in the advisor voice
(switch "Say my typed replies aloud"); the customer answers after it. Needs a one-time model download: `openai/whisper-base.en` (about 290 MB) into the normal
Hugging Face cache (`huggingface_hub.snapshot_download`). The microphone works on localhost or https only.
