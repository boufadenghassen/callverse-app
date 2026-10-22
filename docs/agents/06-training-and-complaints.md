# 6. Training agent (Rim, real) and Complaint agent (Amine, demo)

The **Training agent is real** (the Scenario Generation package by Selim Selmi, integrated and fixed). The **Complaint agent is still a demonstration**: its page exists and works in the browser, but the data comes from the demo gateway, not from the Python service. This document says exactly what exists, what is simulated, what the ideation promised and how to build the Complaint agent the way the others were built.

## Training agent (Rim Ayari, `rim`): REAL, built by Selim Selmi (Scenario Generation)

### Persona and ideation
Rim Ayari, the training lead, says *"I want new advisors to fail safely in training, not live with a real customer."* Her pains: role-plays are manual (she plays the customer herself), hard situations are difficult to reproduce, training is not linked to QA findings. The ideation named the agent *Scenario Generation*. Selim Selmi built it as the package `services/agents/scenario_gen/` (his own README there); the web integration and the fixes below were added on top. Four groups:

| Ideation group | Decision | Built |
|---|---|---|
| Scenario builder (generator, template library, random combinations) | production | **yes**: a catalog of 15 problem types in English, French and Tunisian Arabic (derja), 17 complications, 7 skills; a seeded generator (the same seed always gives the same scenario) |
| Replay and what-if (replay, mutation, change one parameter and compare) | production | **yes**: replay (same seed, or re-seeded), 13 mutation operations (harder, easier, set the language, add an event, add a second problem...), lineage (every copy knows its parent and what changed) |
| Stress and edge cases (multi-event, rare events, difficulty ramp) | prototype | **yes**: generation modes, rare events, and a ramp (the same situation at increasing difficulty) |
| Adaptive training (needs identified from QA weaknesses, recommendations per advisor) | prototype | **yes**: Quality Analyst weaknesses become skill gaps, then a plan of practice scenarios; a progress report compares two QA reports |

### How it works (`scenario_gen/`)
* **Catalog** (`data/catalog.json`): intents (problem types) each with typical customer segments, success criteria and a situation card per language; complications (some rare); the 7 skills (empathy, active listening, de-escalation, accuracy, procedure compliance, resolution, escalation handling); and a map from **QA criteria to skills** (compliance, procedure, accuracy, relevance, satisfaction, sentiment, communication). Criterion names are matched leniently (French or English, accents ignored; "Customer sentiment" is understood as sentiment).
* **Scenario**: `id` (a stable hash of the content), title, category, opening emotion, skills trained, success criteria, complications, the customer's situation card, the trainer's brief, the canonical `spec` (replay and mutation edit it), a `sim` block shaped like the schema of the Customer Sim in the team's contract (`problem_type, difficulty, persona_id, language, gender, max_turns, seed`), and extra fields (`sim_extensions`) outside that contract. Situation cards describe the situation, not the emotion (the rule of `DATA_COLLECTION.md`).
* **Adaptive plan** (`adaptive.py`): each QA score is put on 0 to 1; a score under the threshold (0.7) is a gap of (1 - score) x the criterion's weight on each linked skill; the plan splits the requested number of scenarios between the weakest skills in proportion to the gaps, ramping difficulty from the advisor's current level. Unknown criteria are reported in the plan's rationale. With nothing under the threshold the plan suggests one rare-event scenario to keep the advisor sharp.
* **Optional LLM enrichment** (`llm.py`): `"enrich": true` asks OpenRouter to rewrite only the customer card and the trainer brief; the contract fields never change; with no key, an error or a malformed answer the template text stays and a note says why. The key comes from `OPENROUTER_API_KEY` (a `.env` file, ignored by git; `services/agents/.env.example` shows the names). **No LLM is used unless this is switched on.**
* **Storage**: memory, or a JSON-lines file (`SCENARIO_STORE_PATH`).

### API (agents service, all under `/scenario-gen` except the adapter)
`GET /catalog`, `POST /scenarios/generate`, `POST /scenarios/batch`, `POST /scenarios/ramp`, `GET /scenarios`, `GET /scenarios/{id}` and `/sim` and `/lineage`, `DELETE /scenarios/{id}`, `POST /scenarios/{id}/replay`, `POST /scenarios/{id}/mutate`, `POST /training-plan`, `POST /progress`, `GET /health`; and `GET /training/scenarios`, the flat five-field card list of the web contract (`id, title, profile, difficulty, origin`). Interactive documentation at `/docs`. Also `python -m scenario_gen generate ...` on the command line.

### In the web app (`/training`, role `rim`)
* **Coach plan**: choose an advisor; the page shows that advisor's Quality Analyst report (weakest criterion, coaching tips, latest reports), the **offers to practise today** (the Sales agent's best offers of the day: they belong to customers, so the same list is shown for every advisor and the page says so), and the **automatic focus** (skills with a gap and the reasons).
* **Targeted simulations**: the scenarios generated from that advisor's weaknesses, each opening a **detail page** (situation, trainer brief, complications, success criteria) with *Make harder*, *Make easier*, *Delete* and the lineage.
* **Scenario history**: the latest scenarios with *Replay* (a read) and *What-if harder* (a form that creates a copy).
* **Scenario builder**: choose a difficulty (or any) and press *Generate scenario*: the real generator makes one and its detail page opens (demo mode makes one from a short list).
* All creating actions are **POST** with the CSRF token (`/training/generate`, `/training/scenarios/{id}/mutate`, `/training/scenarios/{id}/delete`); opening a page never creates anything.

### What was fixed when it was integrated
Two of its own tests expected a health answer and a customer segment the service never gave (now checked against what the service answers); the coach ignored the Quality Analyst's "Communication" and "Customer sentiment" criteria (now mapped, with a test that every criterion of the analyst is understood); the *Scenario history* and *Latest reports* lists were always empty (nunjucks' `slice` cuts a list into columns); opening the page with a what-if link created a new scenario at every load (now a POST); the *Generate scenario* button still ran the old in-browser demo (now calls the generator); the sales offers were rotated per advisor, which invented a pairing (now team-wide and labelled); `.env.example` was mentioned but absent (added, and the real `.env` stays ignored).

### Tests
`services/agents/tests/` (83 tests of the generator, mutations, catalog, adaptive plan, store, LLM with a fake transport, API and the contract against a verbatim copy of the Customer Sim schema), web `workforce.spec.ts` (the gateway and the coach flow) and `training.spec.ts` (the builder, validation, no creation on a page load, team-wide offers, the gateway), and one browser test of the builder and what-if.

### Honest limits
* **Not connected to our customer simulator yet.** The `sim` block follows the Customer Sim schema of the team's contract (`problem_type`, `persona_id`...), which is not the input of our simulator (`persona`, `intent`, `difficulty`, `memory`). A scenario can be read and varied here, but the live call in the advisor console does not start from it.
* The Tunisian Arabic cards are drafts: a native speaker must read them before a demo. The LLM path is tested with a fake HTTP transport only, not against the live service.
* The coaching threshold is 70 %: with the simulated calls (averages around 85) most advisors show no weakness and get the maintenance scenario. Trainer-facing text is English only.
* The Quality Analyst already attaches a training scenario to every rule and builds a coaching plan per advisor ([04-quality-analyst.md](04-quality-analyst.md)); the coach uses the criteria averages, not yet those rule-level scenarios.

## Complaint agent (Amine Jebali, `amine`)

### Persona and ideation
Amine Jebali, the complaint manager, says *"A complaint isn't closed when it's answered, it's closed when it's resolved and trusted again."* His pains: complaints arrive with an incomplete case history, root causes are rediscovered by hand case by case, deadlines are tracked in scattered tools. Four groups:

| Ideation group | Decision | In the app today |
|---|---|---|
| Triage and routing (priority, severity, escalation risk) | production | **demo**: severity lanes with an escalation-risk ring per case |
| Early warning (critical cases, supervisor alerts) | prototype | **demo**: a banner for any case with an escalation risk of 80 or more |
| Complaint insight (history, root causes, trends) | prototype | partial: a root-cause cluster per case, no trend view |
| Prediction and recovery | perspective | not built (kept for later) |

### What the page does (`/complaints`)
* **Demo data** (`openComplaints()`): `CMP-221` "Charged twice, third contact this month" (Critical, escalation risk 87, cluster *Billing duplicates*, 6 h left), `CMP-219` "Roaming bundle not applied abroad" (High, 64, *Roaming activation*, 20 h), `CMP-214` "Contract cancellation fee disputed" (Medium, 41, *Contract terms*, 46 h).
* Cases are sorted into **Critical, High and Medium lanes**; a summary shows the number of open cases, the number critical and the average escalation risk; each case shows its risk ring and a deadline meter (hours left out of 48).
* The **early warning** banner "may escalate within n h, alert a supervisor now" appears for risk of 80 or more (here CMP-221) with an *Alert supervisor* button (a confirmation only: nothing is sent).
* *Take case* (a confirmation), *Escalate* (moves the card up one lane in the browser) and **drag and drop** between lanes (browser only; nothing is saved).

### How to build the real agent
1. Contract: `GET /complaints/open` returns `ComplaintCase[]` (`id, summary, severity, escalationRisk, cluster, hoursLeft`).
2. `services/agents/complaints.py`: severity and urgency from the text and the customer file (the customer 360° and the quality analyst's reviews are the natural inputs: repeat contacts, unresolved calls, hang-ups); **root-cause clustering** with the same TF-IDF or embeddings used by the advisor and the quality analyst; an escalation risk from the open ticket count, transfers, mood and deadline; deadlines from a policy table.
3. Same wiring as the other agents (route, test, gateway override, README tick). Trend views come from the stored history, as the quality analytics do.

## Honest status
The Training agent runs in the Python service and is tested; it is not yet wired into the live call. The Complaint page is a **demonstration**: three fixed rows and interactions that run in the browser, with no machine learning behind it.

## Files
Training: `services/agents/scenario_gen/` (with its own README), `services/agents/tests/` (its tests), `app/src/pages/pages.controller.ts` (the `/training` routes), `app/views/training.njk` and `training-scenario.njk`, `app/src/agents/*gateway.ts` (scenario methods), `app/test/training.spec.ts`, `app/test/workforce.spec.ts`. Complaints: `app/src/agents/mock.gateway.ts` (`openComplaints`), `app/views/complaints.njk`, `app/src/pages/pages.controller.ts`, `app/client/app.ts` (escalate, drag and drop), `app/src/pages/deck-content.ts`.
