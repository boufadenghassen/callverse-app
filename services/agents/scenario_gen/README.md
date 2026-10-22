# Scenario Generation Agent (Training Lead)

Owner: Rim Ayari. Part of the orqestra agents service (`services/agents`, FastAPI, one router per agent).

Pain point it answers: *role-play is manual, so advisors learn on real customers.* This agent builds the practice
scenarios, so advisors can train on any situation safely before facing it live.

```
QA weaknesses ──► Scenario Gen ──scenario──► Customer Sim ──calls──► Advisor ──transcript──► Quality Agent
        ▲                                                                                        │
        └────────────────────────── QA weaknesses -> new training scenarios ──────────────────────┘
```

## What is built (the four ideas of the ideation slide)

| Idea | Where | Endpoints |
|---|---|---|
| **Scenario builder**: template library, random and automatic generator | `catalog.py`, `data/catalog.json`, `generator.py` | `GET /catalog`, `POST /scenarios/generate`, `POST /scenarios/batch` |
| **Replay & what-if**: replay, what-if, mutation | `mutations.py`, `store.py` | `POST /scenarios/{id}/replay`, `POST /scenarios/{id}/mutate`, `GET /scenarios/{id}/lineage` |
| **Stress & edge cases**: multi-event, rare events, difficulty ramp | `generator.py` (`mode`, `ramp_specs`) | `generate` with `mode`, `POST /scenarios/ramp` |
| **Adaptive training**: recommendations from QA weaknesses | `adaptive.py` | `POST /training-plan`, `POST /progress` |

All endpoints are under `/scenario-gen`. Interactive docs at `/docs`.

## Run it

Python 3.10 or newer.

```bash
cd services/agents
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest                                        # 83 tests, under a second
uvicorn main:app --reload --port 8000                   # http://localhost:8000/docs
python -m scenario_gen generate --difficulty 4 --language derja --mode multi_event --seed 7
```

No API key is needed for anything except `"enrich": true`.

## The contract with the Customer Sim

Each scenario has a `sim` field that is **field for field the `Scenario` model of the Customer Sim**
(`problem_type, difficulty, persona_id, language, gender, max_turns, seed`). `GET /scenarios/{id}/sim` returns only that.
`tests/test_contract.py` validates everything we generate against a verbatim copy of his schema file
(`tests/fixtures/customer_sim_schemas.py`); if he changes his schema, replace the fixture and rerun the tests.

Assumptions to confirm with him:

1. **`problem_type` keys.** We use our own 15 intent keys (`double_billing`, `line_cut`, `cancellation_request`...).
   They must exist in his `intents.json`. Check with `python -m scenario_gen check-intents path/to/intents.json`,
   or set `CUSTOMER_SIM_INTENTS_PATH` and we only generate keys he knows.
2. **`persona_id`** is built as `<language>_<f|m>` (`derja_m`, `fr_f`, `en_m`), copying his example.
3. **Extra fields.** His `Scenario` cannot carry complications. We expose them in `sim_extensions`
   (`segment, opening_emotion, events, extra_intents, hidden_intent`), outside the contract, ignored today.
   His `Profile` already has `intents` (ordered) and `hidden_intent`, so these map directly if he adds them.
   `complications` (English text of each event) can go into his prompts as they are.

## The scenario

```jsonc
{
  "id": "sc_a779891e13",              // stable hash of the content
  "kind": "generated",                // generated | ramp | replay | mutation | adaptive
  "title": "...", "category": "complaint", "opening_emotion": "disgust",
  "skills": ["escalation_handling", "empathy", ...],       // what it trains
  "success_criteria": ["Listens without interrupting", ...],
  "complications": ["The customer interrupts the advisor...", ...],
  "customer_card": "...",             // the situation, in the scenario's language (en, fr, derja)
  "trainer_brief": "...",
  "spec": { ... },                    // the canonical definition: replay and mutation edit this
  "sim": { ... },                     // send this to the Customer Sim
  "sim_extensions": { ... }
}
```

Same seed gives the identical scenario. Situation cards follow the "situation, not emotion" rule of `DATA_COLLECTION.md`.

## Replay and what-if

* `replay` returns the identical scenario (same seed). `{"reseed": true}` keeps the situation with new randomness.
* `mutate` takes `ops` from: `harder, easier, set_difficulty, set_language, set_gender, set_intent, set_segment,
  set_max_turns, add_event, remove_event, add_second_problem, set_hidden_intent, reseed`, or `{"random": true}`.
  Example: `{"ops": [{"op": "set_language", "value": "derja"}, {"op": "add_event", "value": "threatens_to_leave"}]}`.
* Every mutation keeps `parent_id` and a readable `mutation_log`.

## Adaptive training (placeholder input)

`POST /training-plan` with `{"advisor_id": "...", "weaknesses": [{"criterion": "Sentiment", "score": 35}, ...]}`.
Scores can be 0 to 1 or 0 to 100. Criteria are matched leniently (French or English, accents ignored): conformité,
pertinence, exactitude, respect des procédures, satisfaction, sentiment, or a skill name. Scores under `threshold`
(default 0.7) become skill gaps; the plan splits `size` scenarios between the weakest skills and ramps the difficulty up
from `current_level`. Unknown criteria are reported in `rationale`, not fatal. **When the Quality Agent's real output
format is known, only `normalize_weaknesses` in `adaptive.py` needs to change.** `POST /progress` compares two QA
reports (improved, regressed, unchanged) to close the loop.

## LLM enrichment (optional)

`"enrich": true` asks OpenRouter to rewrite `customer_card` and `trainer_brief` for variety. The contract fields never
change. If there is no key, the call fails or the answer is malformed, the scenario keeps its template text and a note
explains why. Set the key in `.env` (copy `.env.example`), never in code.

## Known limits

* **Derja cards are my drafts.** Please have a native speaker read them (`data/catalog.json`) before a demo.
* The LLM path is tested with a mocked HTTP transport only, not against the live OpenRouter API.
* Storage is memory, or a JSON-lines file with `SCENARIO_STORE_PATH`. Postgres can replace `store.py` later.
* The web app is wired in HTTP mode: `HttpAgentGateway.scenarios()` calls
  `GET /training/scenarios`, which returns the flat five-field scenario-card contract.
* Trainer-facing text (titles, criteria, briefs) is English only.

## Files

```
main.py                     the service entry point (all agent routers, including Scenario Gen)
scenario_gen/
  schemas.py                contract (SimScenario) and our own models
  catalog.py + data/catalog.json   15 intents x 3 languages, 17 complications, skills, QA criteria map
  generator.py              builder, random, modes, ramp
  mutations.py              what-if operations
  store.py                  history and lineage
  adaptive.py               QA weaknesses -> training plan, progress
  llm.py                    OpenRouter enrichment with fallback
  service.py, router.py     orchestration and HTTP
  __main__.py               command line
tests/                      83 tests, including the contract test
```
