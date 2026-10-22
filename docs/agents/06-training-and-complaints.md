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

## Complaint agent (Amine Jebali, `amine`): REAL

### Persona and ideation
Amine Jebali, the complaint manager, says *"A complaint isn't closed when it's answered, it's closed when it's resolved and trusted again."* His pains: complaints arrive with an incomplete case history, root causes are rediscovered by hand case by case, deadlines are tracked in scattered tools. Four groups:

| Ideation group | Decision | Built |
|---|---|---|
| Triage and routing (priority, severity, escalation risk) | production | **yes**: every case is read for its root cause, scored for severity and escalation risk with the reasons in points, and given a deadline from its level |
| Early warning (critical cases, supervisor alerts) | prototype | **yes**: a warning for a case with an escalation risk of 80 or more, past its deadline, or about to be with a high risk; *Alert supervisor* is recorded in the case log |
| Complaint insight (history, root causes, trends) | prototype | **yes**: the case file (customer history, earlier cases, log, what worked on similar cases) and a view of root causes with the trend of the last 28 days against the 28 before, time to resolve, deadlines met, repeat contacts |
| Prediction and recovery | perspective | **partly**: recovery is built (a resolved case waits for a follow-up call after 72 hours and is closed only if the customer trusts us again; otherwise it comes back); **no learned prediction** |

### Status
**Real.** Code: `services/agents/complaints_agent/` (own README there). The rules are phrase patterns and hand-weighted factors; no language model. **The cases, customers, deadlines and policies are invented, and the history behind the trends is simulated.**

### How it works
1. **Root cause** (`engine.classify`): nine clusters (billing duplicates, bill amount disputed, roaming activation, contract terms and fees, network and service quality, data usage, repeat contact, advisor conduct, device or SIM) defined by phrases in `knowledge/complaints.json`; the cluster with the most phrase hits wins and the others that also matched are listed. Each cluster has a kind of root cause (process, knowledge gap, soft skills, policy, tools, network), the team that owns it, the usual first action and the usual ways it is resolved.
2. **Severity** (how much is at stake), a sum of named factors from 0 to 100: **money at stake** (+25 from 300 TND, +15 from 100, +8 from 30, read from "180 dinars", "$2,000"), **legal exposure** (+30: lawyer, court, consumer protection, regulator), **public exposure** (+12: post online, social media, press), **customers affected** (+10: the whole building, everyone), **customer value** (up to +15: 5 years or more, premium plan, 100 TND a month or more) and **repeat contact** (+8 for one earlier contact, +16 for two or more: the customer's other cases in the last 30 days, or "third time" in their words). **Level**: Critical from 50, High from 30, Medium from 15, Low below.
3. **Deadline**: from the level (Critical 12 h, High 24 h, Medium 48 h, Low 72 h); the hours left can go negative (the case is late). A level set by hand uses the deadline of the new level.
4. **Escalation risk** (how likely it is to escalate), a sum from 0 to 100: starting point +10, **threatens to escalate** (+25 legal, +15 public), **risk of losing the customer** (the sales agent's churn risk x 0.2, at most +20), **time pressure** (+8 from half the deadline used, +15 from 75 %, +25 when late), **repeat contacts** (+6 each, at most +18), **tone** (+10 for words such as unacceptable or fraud, else +5 when the customer file says angry or frustrated), **passed around** (+8 for two transfers or more), **customers affected** (+5), **nobody owns it** (+8 once a quarter of the deadline is used and the case is still not taken) and **someone is on it** (-8).
5. **First actions**, each with its reason and who does it: the usual action of the cluster; a supervisor's approval when the amount is above the 50 TND refund limit; compliance when the customer mentions a lawyer or a regulator; a reply within 2 hours when the customer may post publicly; one owner and no more transfers after repeat contacts; an apology when the deadline passed; a supervisor alert when the risk is 80 or more; and always a written confirmation and a call back after 72 hours.
6. **Life of a case** (`store.py`, SQLite `data/complaints.db`, git-ignored, `COMPLAINTS_DB` moves it): **open**, **taken** (by whom), **resolved** (with how: refund or credit, fault fixed, explained, goodwill, supervisor, nothing possible), **closed** after the follow-up call when the customer is satisfied; if the customer is still unhappy the case **reopens**. *Escalate* moves it one level up (and *set the level* sets it); every move is in the case log with who, when and a note. The analysis is not stored: it is worked out again from the text, the customer file and the other cases each time, so a change of rules shows at once; only a level set by hand is kept.
7. **Where complaints come from** (`GET /complaints/insights`): cases per week, root causes, per cluster the last 28 days against the 28 before (trend), open now, average time to resolve and what usually works (the most common resolution), deadlines met, customers satisfied at the follow-up and cases that came back, repeat-contact rate.
8. **From calls**: calls the quality analyst scored where the customer hung up, left in a mood of 25 or less or nothing was agreed, and that are not a case yet, are listed with how the agent would read them; one click opens the case with the customer's own words from the call.
9. **Simulated history**: an empty store is filled with 40 resolved cases over eight weeks (roaming complaints rise in the last three weeks) and today's six open cases, the first three being the demo cases of the page. The cases age in real time: after a day they are late, and deleting `data/complaints.db` restarts the demo clock.

### API (agents service, under `/complaints`)
| Endpoint | Input | Answer |
|---|---|---|
| `GET /complaints/open` | none | the open cases, most dangerous first: the contract's `ComplaintCase` fields plus `severityScore`, `severityFactors[]`, `riskFactors[]`, `deadline`, `warning`, `actions[]`, `contacts`, `amount`, `customer`, `status`, `assigned`... |
| `GET /complaints/{id}` | `CMP-n` | the case in full: the words, the analysis, the log, earlier cases of the customer, the customer file, similar resolved cases and what worked |
| `POST /complaints/triage` | `text` (10 to 1,500 characters), `customer_id` (optional) | the analysis of a complaint that is not saved |
| `POST /complaints` | the same plus `channel` (call, email, chat, social, branch, app) | opens a case |
| `POST /complaints/{id}/{action}` | `by`, `note`, and `resolution` (resolve), `level` (severity), `trusted` (close) | the case after the move: `take`, `escalate`, `severity`, `alert`, `resolve`, `close`, `reopen`; a wrong move is 422, unknown case or action 404 |
| `GET /complaints/follow-ups`, `GET /complaints/insights`, `GET /complaints/from-calls`, `POST /complaints/from-call` | | as described above |

### In the web app (`/complaints` and `/complaints/{id}`, role `amine`)
* **Open complaints**: an early warning banner for each case that needs a supervisor (with *Alert supervisor*); numbers (open, critical, average escalation risk, past their deadline, waiting for the follow-up call); **Read a complaint** (paste or pick a sample, *Read it* shows the root cause, level, the two scores with their reasons, the deadline and the first actions without saving; *Open this case* saves it); four **lanes** (Critical, High, Medium, Low) with a card per case (root cause, customer, owner, escalation risk ring, hours left or late, *Why* with every factor in points, *Take case*, *Escalate*, *Open*); **Waiting for the follow-up call**; **Calls that may be complaints**; **Where complaints come from**.
* **A case** (`/complaints/{id}`): what the customer said, the risk ring and deadline, **why this level and this risk**, **what to do first** with what usually worked, the customer's history and earlier cases, the log, and the moves that fit its status (take, escalate, alert, set the level by hand, resolve with how, close after the follow-up call or reopen).
* Every move is a form with the CSRF token, done in the name of the signed-in user; a refusal comes back to the page with its message. In **demo mode** (no real agents) the page keeps its three demo cards with drag and drop in the browser and nothing saved.

### Explainability
Severity and escalation risk are sums of named, signed, worded factors, shown for every case; actions say why they are there and who does them; the level and the deadline follow from the policy table; what usually works comes from the stored cases and says how many.

### Tests
Python (14): money read from text, the root-cause clusters, severity as a sum and what drives it, repeat customers and value, the deadline and time pressure, the first actions and the refund limit, the whole life of a case with its log, a customer who is still unhappy reopens the case, escalate and alert, the simulated history, the insights, a case in full, the API with its refusals, cases from calls. Web (6, `complaints.spec.ts`): roles and demo mode, the page with the real agent's data, a case in full, moves guarded and validated and done by the signed-in user, reading and opening complaints, the gateway. Browser (1 new): cases with their reasons, a complaint read, opened, taken, resolved and closed after the follow-up; accessibility audit clean on both pages.

### Honest limits
Patterns and hand-weighted factors, not a language model or a trained model: a paraphrase can be missed, a loose phrase over-read, and the weights are judgements, not measurements. Everything is invented or simulated (customers, policies, deadlines, the history behind the trends). The escalation risk says how likely a case is to escalate; it does not predict when. There is no link yet to a real ticketing system, e-mail or chat, and no notification is sent when a supervisor is alerted (it is recorded in the log). A call can open a case, but the customer on a call is not identified, so the repeat-contact count does not apply to it. **Not built**: a learned prediction of escalation or churn from real data, deadlines that depend on opening hours, automatic assignment to an agent.

## Honest status
The Training agent runs in the Python service and is tested; it is not yet wired into the live call. The Complaint page is a **demonstration**: three fixed rows and interactions that run in the browser, with no machine learning behind it.

## Files
Training: `services/agents/scenario_gen/` (with its own README), `services/agents/tests/` (its tests), `app/src/pages/pages.controller.ts` (the `/training` routes), `app/views/training.njk` and `training-scenario.njk`, `app/src/agents/*gateway.ts` (scenario methods), `app/test/training.spec.ts`, `app/test/workforce.spec.ts`. Complaints: `app/src/agents/mock.gateway.ts` (`openComplaints`), `app/views/complaints.njk`, `app/src/pages/pages.controller.ts`, `app/client/app.ts` (escalate, drag and drop), `app/src/pages/deck-content.ts`.
