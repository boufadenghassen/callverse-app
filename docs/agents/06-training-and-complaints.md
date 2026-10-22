# 6. Training agent (Rim) and Complaint agent (Amine): demo agents

These two agents are **not built as real agents yet**. Their pages exist, work in the browser and are part of the demonstration, but the data comes from the demo gateway or from the browser script, not from the Python service. This document says exactly what exists, what is simulated in the page, what the ideation promised and how to build the real thing in the same way as the other agents.

## Training agent (Rim Ayari, `rim`)

### Persona and ideation
Rim Ayari, the training lead, says *"I want new advisors to fail safely in training, not live with a real customer."* Her pains: role-plays are manual (she plays the customer herself), hard situations are difficult to reproduce, training is not linked to QA findings. The ideation named the agent *Scenario Generation* (owner in the team table: Selim). Four groups:

| Ideation group | Decision | In the app today |
|---|---|---|
| Scenario builder (generator, template library, random combinations) | production | **page demo**: "Generate scenario" in the browser |
| Replay and what-if (replay, mutation, change one parameter and compare) | production | **page demo**: Replay (message only) and What-if (a random single change, side by side) |
| Stress and edge cases (multi-event, rare events, difficulty ramp) | prototype | partial: three difficulty levels, no automatic ramp |
| Adaptive training (needs identified from QA weaknesses, recommendations per advisor) | prototype | partial: each scenario shows the QA weakness it came from; and the quality analyst already produces the data (below) |

### What the page does (`/training`)
* **Demo data** (`MockAgentGateway.scenarios()`): three scenarios, `SC-31` "Double charge, customer threatens to post online" (Unsatisfied, Hard, origin "QA weakness: compliance"), `SC-30` "First call from a new subscriber about data limits" (New, Easy, "Template library"), `SC-29` "Premium customer, two intents, transferred once" (Premium, Medium, "What-if mutation").
* **Scenario builder** (in `client/app.ts`, no server): a random combination of a customer profile (new subscriber, premium client, unhappy long-time client, anxious first-time caller), a problem (charged twice, roaming bundle unusable, cancellation fee disputed, data limits not matching the plan, transferred twice) and a goal (immediate refund, written confirmation, lower price, a supervisor), with an optional difficulty. The new card gets the next `SC-n` id.
* **Replay** shows a message. **What-if** changes exactly one parameter at random (difficulty, customer profile, or adds the event "calling for the third time"), and shows the original and the mutated scenario side by side with the changed part highlighted and a sentence saying what to compare.
* Nothing is stored; the scenarios are not played against the customer simulator yet.

### What already exists on the data side
The **quality analyst** attaches to every rule a **training scenario to practise** (for example "Double charge, customer asks for an immediate refund" for the rule *promise before the policy check*; "Angry premium customer, third contact" for *no empathy*) and builds a **coaching plan per advisor** from their most frequent errors ([04-quality-analyst.md](04-quality-analyst.md)). That is the "QA weaknesses to new training scenarios" arrow of the agent architecture; the Training agent only has to consume it.

### How to build the real agent
1. Contract (`app/README.md`): `GET /training/scenarios` returns `Scenario[]` (`id, title, profile, difficulty, origin`).
2. `services/agents/training.py`: take the scenario templates from the customer simulator (personas, intents, difficulties, memory) and from the quality rules' scenarios; add a generator and a mutation function (change one parameter, keep a record of which).
3. Route in `main.py`, test in `tests/test_agents.py`, override `scenarios()` in `HttpAgentGateway`, tick the endpoint in the README. Then let Replay start a real live call with the customer simulator (`startCall`) so a scenario can be played, not just displayed.

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
Both pages are **demonstrations**: the data is three fixed rows each, and the interactions run in the browser. They show what the real agents will look like and exercise the gateway and the roles, but no machine learning stands behind them.

## Files
`app/src/agents/mock.gateway.ts` (`scenarios`, `openComplaints`), `app/views/training.njk`, `app/views/complaints.njk`, `app/src/pages/pages.controller.ts` (routes), `app/client/app.ts` (builder, replay, what-if, drag and drop, escalate), `app/src/pages/deck-content.ts` (the ideas table with each idea's decision and coverage).
