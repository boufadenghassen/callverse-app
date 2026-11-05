# 3. Workforce manager (Sana, workforce)

## Purpose and persona
Sana Gharbi, the workforce manager, says *"I need to see problems before they happen, not after."* The agent forecasts the calls of a queue, tells how many advisors a queue needs, lets her **simulate a decision before applying it**, suggests which advisor should work which queue, and plans lunches. The ideation (agent name: *Workforce Manager Agent (RL)*) had four groups: forecast and monitor, routing and allocation, scheduling and staffing, risk and emergencies.

| Ideation group | Decision | Built |
|---|---|---|
| Forecast and monitor | production | **yes**: seasonal forecast, hour-by-hour load, waiting time and service level |
| Routing and allocation (RL) | production | **yes, RL shadow policy**: constrained Q-learning with the local-search fallback |
| Scheduling and staffing | prototype | **yes**: what-if simulation, lunch plan, overtime estimate |
| Risk and emergencies | perspective | no (kept for later) |

## Status
**RL is implemented in shadow mode.** The constrained Q-learning policy learns allocation actions from the workforce simulator, masks invalid actions, checks hard safety constraints, and proposes actions without changing the active schedule. The local-search planner remains a deterministic fallback and evaluation baseline. The bootstrap dataset now combines a verified **CC0 public call-center dataset** with synthetic episodes. The public source contains daily aggregates only, so its derived 15-minute rows are explicitly labelled `real_daily_disaggregated`; they are not claimed to be observed interval measurements.

### Workforce data seed

The real source is Kaggle's [Call Center Data](https://www.kaggle.com/datasets/satvicoder/call-center-data), released under **CC0 Public Domain**. It contains incoming calls, answered calls, abandoned calls, answer speed, average talk duration, average waiting time and service level, but no timestamps, queue labels or advisor identities.

Run the seed after downloading the source file to `datasets/workforce-real/Call Center Data.csv`:

```powershell
python services/agents/workforce_data.py
```

This writes the ignored file `datasets/workforce-real/mixed-workforce-15m.jsonl`. Each row includes a `source` field:

* `real_daily`: the untouched public daily aggregate loaded by `load_real_daily()`.
* `real_daily_disaggregated`: a derived 15-minute bootstrap row, using an explicit synthetic intraday profile and queue mix.
* `synthetic`: an independently generated simulator episode.

The real-derived rows are used for calibration and final holdout evaluation; synthetic rows are used for bootstrap training and stress scenarios. They must not be randomly mixed across train and test by row. The workforce chart now splits real days by day: earlier days form the forecast baseline and the latest day is shown as the actual holdout, both disaggregated to the displayed hourly profile. A future operational adapter must replace the disaggregation step with native timestamped 15-minute aggregates.

## The call center in the model
* Open 9:00 to 18:00 (nine hours, 9h to 17h). The demo day is frozen at 13:00: hours up to 13h have an *actual*, later hours do not.
* **Five queues**, each with typical calls per hour (9h to 17h) and an average handling time (AHT):

| Queue | Name | AHT (s) | Typical calls per hour, 9h..17h |
|---|---|---|---|
| A | Billing | 270 | 30, 42, 58, 70, 78, 84, 70, 55, 40 |
| B | Plans and billing, premium | 300 | 20, 28, 40, 52, 60, 72, 60, 45, 35 |
| C | Roaming | 360 | 10, 14, 18, 22, 24, 26, 22, 18, 14 |
| D | Technical | 420 | 14, 20, 26, 32, 36, 40, 34, 26, 20 |
| E | Sales | 200 | 8, 12, 16, 20, 22, 24, 20, 16, 12 |

* **Service target**: 80 % of calls answered within 20 seconds.

## Method 1: the forecast
* **History** (synthetic): for each queue, 8 weeks x 5 weekdays x 9 hours of call counts, drawn from a Poisson distribution around the typical shape times a weekday factor (Monday 1.10, Tuesday 1.00, Wednesday 0.97, Thursday 1.00, Friday 0.93). The random seed is fixed per queue, so the history is always the same.
* **Seasonal profile**: the average of the same hour over the past weeks, for the weekday of the demo day (Wednesday).
* **Intraday correction**: how is today running against its profile? ratio = (calls so far) / (profile so far), clipped to 0.8 to 1.25; half of the gap is carried into the hours to come: forecast = profile x (1 + (ratio - 1) / 2).
* Today's actuals are also synthetic: the typical shape times a "busy today" factor per queue (A 1.15, B 1.08, C 0.85, D 0.90, E 0.80), so billing is busy and the rest quiet.
* Example, queue B: actual 24, 29, 55, 68, 64 for 9h to 13h; forecast 19, 25, 40, 49, 63, then **81 calls at 14h** (the spike), 61, 53, 41.

## Method 2: staffing with Erlang C
The standard queueing formula for a call center (checked against the textbook by a test).
* Load in erlangs `a = calls per hour x AHT / 3600`.
* `erlang_c(n, a)`: the probability that a caller has to wait with `n` advisors (computed with the Erlang B recursion, stable for large `n`); 1 when `n <= a`.
* **Average wait** = P(wait) x AHT / (n - a), capped at 15 minutes (an overloaded queue is shown as 900 s, not infinity).
* **Service level** = 1 - P(wait) x exp(-(n - a) x 20 / AHT).
* **Advisors needed** = the smallest `n` whose service level reaches 80 %.
* **Rosters** (advisors on duty per hour) are planned on 85 % of the typical demand, so that a normal peak runs short: that is exactly what the what-if is for. Rosters per queue, 9h to 17h: A 4,5,6,7,8,8,7,6,5; B 3,4,5,6,7,8,7,6,5; C 3,3,4,4,4,5,4,4,3; D 4,4,5,6,6,7,6,5,4; E 2,2,2,3,3,3,3,2,2.

## Method 3: the what-if simulation
`simulate(queue, extra advisors, from, to)`: for every hour that overlaps the window it takes the forecast and the roster, adds (or removes) `extra` advisors, and recomputes wait and service level with Erlang C; the window's average is weighted by calls x share of the hour inside the window. It returns the before and after (wait, service level), **the hour-by-hour table** (calls, advisors, simulated advisors, wait and service level before and after, advisors needed) and ranked recommendations: add advisors where the service level is furthest below target; move a spare advisor from another queue that has more than it needs; offer a callback when the wait passes 3 minutes; warn when removing advisors hurts.
Example (queue B, +2 advisors, 14:00 to 16:00): average wait **99 s to 13 s**, service level **58 % to 89 %**; the first recommendation: *"Add 2 advisors on queue B at 14h: 81 calls expected, 10 advisors are needed to answer 80% within 20 s (now 49%)."*

## Method 4: routing and allocation (`routing.py`) — current baseline
*Which advisor should work which queue for the rest of the day.* **This section documents the local-search fallback, not the primary RL policy.** It remains the deterministic safety fallback and benchmark that the RL policy must beat. It must not be deleted: it provides safe actions when the policy is unavailable, out of distribution, or violates a constraint.
* **Advisor pool**: 31 synthetic advisors (named by queue and number, for example `C02`); every second advisor is cross-skilled. Cross skills: A can also serve B; B: A; C: D and A; D: C and E; E: D.
* **Objective**: the priority-weighted number of calls answered within 20 s, sum over queues of priority x calls x service level. Priorities: A 1.0, B 1.3 (premium, counts 30 % more), C 0.9, D 1.0, E 0.8.
* **Search**: for each remaining hour, start from today's roster, and repeatedly make the **single move** of a cross-skilled advisor to another queue that raises the objective most, at most 6 moves per hour, each move having to win at least 0.05 weighted calls. A **guard** protects the donor queue: it may not fall below 65 % service (or below what it has now if it is already lower).
* **Explanation of every move**: for example *"Move C02 (skills C, D, A) from queue C to queue A at 14h: queue A goes from 47% to 71% within 20 s, queue C from 87% to 67%."*
* **Independent check**: a discrete-event simulation (Poisson arrivals, exponential handling times, first come first served, 60 repetitions, the first hour of each run discarded) re-measures the gain without using the formula. Result today: **3 moves, 68 % to 72 % by the formula, 70 % to 74 % in the simulation.**

## Implemented: constrained workforce RL

The agent learns **allocation decisions**, not direct control of a live queue. The current policy uses tabular Q-learning over bounded cross-skilled reassignments for the next interval, validates each proposal with a policy guard, and exposes it in shadow mode beside the deterministic fallback. Adding or removing people, breaks, overtime and callbacks remain separate actions for later policy versions.

### RL formulation

* **Environment**: the current `rl_workforce.py` policy trains against the deterministic workforce simulator; the production migration target is a Gymnasium-compatible `WorkforceEnv` backed by a calibrated discrete-event simulator. The simulator must reproduce arrival bursts, abandonment, handling-time distributions, occupancy, skills, breaks, shrinkage, absences and queue priority. It is the training environment, never the source of production truth.
* **Observation**: per-queue interval forecast and error bounds, current queue length and oldest wait, arrivals, abandons, service level, AHT, occupancy, available advisors, skills, breaks, absences, interval-of-day, day-of-week, holidays and the previous action. Features are versioned and normalized using training-set statistics.
* **Action**: a masked, bounded reassignment matrix (advisor or skill group to queue), plus optional `no-op`. Invalid skills, unavailable advisors, duplicate assignments and unsafe moves are masked before inference.
* **Reward**: weighted service level and abandonment reduction, minus waiting time, overtime, occupancy, unnecessary moves and fairness penalties. Premium-queue priority is a business configuration, not a hidden model weight. Reward components are logged separately so operations can challenge the trade-off.
* **Constraints**: minimum service level per queue, maximum occupancy, maximum consecutive work, break compliance, staffing minimums, skill eligibility and a change budget per interval. A constrained policy is preferred to an unconstrained reward with very large penalties.
* **Training target**: first outperform the current local-search baseline and an OR-Tools feasibility/optimization baseline on the same held-out scenarios, with confidence intervals and no regression on any protected queue. The current bootstrap policy is not promoted until it passes these gates.

### Selected tools

| Need | Selected tool | Why |
|---|---|---|
| Environment and tests | **Current simulator; Gymnasium migration target** | The current bootstrap is runnable without optional packages; Gymnasium is the target standard for `reset`/`step`, reproducible seeds and action-mask wrappers. |
| RL training and serving | **Current tabular Q-learning; Ray RLlib migration target** | Q-learning provides the implemented RL baseline. RLlib is the production target for distributed training, policy modules and long-running inference. |
| Hard feasibility and fallback | **Google OR-Tools CP-SAT** | Encodes skills, coverage, breaks, maximum moves and labor rules as hard constraints. It is the safety fallback and can generate expert demonstrations for warm-start/offline training. |
| Simulation | **SimPy** plus domain code | Event-driven arrivals, queues, abandonment and service completions; calibrated from real aggregates and replayable with fixed seeds. |
| Experiment tracking and registry | **MLflow** | Stores dataset/simulator/policy versions, reward components, constraint violations, evaluation artifacts and promotion approvals. |
| Data and operational state | **PostgreSQL** for durable workforce data; **Redis** for short-lived forecasts, locks and inference cache | Replaces SQLite files for concurrent production use without putting operational state in the model process. |
| Metrics and traces | **OpenTelemetry**, Prometheus and Grafana | Correlates inference with the decision interval and exposes latency, fallback rate, drift, constraint violations and realized outcomes. |

The runnable RL policy is in `services/agents/rl_workforce.py` and uses tabular Q-learning with the current simulator. Ray RLlib, Gymnasium and SimPy are the production migration stack listed in `services/agents/requirements-rl.txt`; the web API does not import those optional training libraries for the bootstrap path. OR-Tools remains a runtime dependency only if the fallback is computed online. MLflow, PostgreSQL, Redis and telemetry are deployment concerns and should be optional for the local demo.

### Data and learning loop

1. Ingest interval aggregates from the contact-center platform: offered calls, answered calls, abandonment, queue wait, AHT, advisor state, skills, schedules, absences and applied assignments. The current bootstrap reads the CC0 daily source through `workforce_data.py`; do not send customer text, audio or unnecessary personal data to the RL pipeline.
2. Build an immutable, time-ordered decision log containing `state`, `action_taken`, `policy_version`, constraints, forecast version, reward components and observed next state. Use an event id and interval id for idempotency.
3. Backfill and validate the simulator against held-out historical intervals. Calibrate arrival and AHT distributions, abandonment curves and advisor availability; record calibration error by queue and time slice.
4. Train offline on historical behavior and OR-Tools/baseline demonstrations. Split by date, not random rows, to prevent leakage. Evaluate on unseen days, peak periods, absences and forecast-error stress tests.
5. Register a candidate in MLflow only when it passes the gates below. Run it in shadow mode, comparing its proposed action with the applied baseline without affecting schedules.
6. Canary the policy for one queue or one interval class. Expand only after operations approval and automatic rollback checks. Retrain on a fixed cadence and whenever drift or a business-rule change invalidates the simulator.

### Production decision path

`forecast -> feature validation -> policy inference -> action mask -> OR-Tools/policy guard -> baseline fallback if needed -> human approval or configured auto-apply -> event log -> outcome metrics`

The inference endpoint must be stateless and versioned, return the policy id, feature timestamp, action, constraint checks, confidence/uncertainty proxy and fallback reason, and complete within the operational decision budget. A timeout, stale forecast, missing feature, model load error or constraint failure is an explicit fallback event, never a success-shaped empty recommendation.

### Safety, governance and rollout gates

* **Never auto-apply initially.** Start with shadow mode, then human-approved recommendations. Auto-apply is allowed only for a bounded change budget and approved queues.
* **Hard stop** on skill violations, understaffing, occupancy above the configured ceiling, break/labor-rule violations, missing data, stale data or policy/model version mismatch.
* **Fallback** to the current local search, then to the last approved schedule if the fallback cannot solve the constraints.
* Compare against the local-search and OR-Tools baselines on service level, P95 wait, abandonment, occupancy, overtime, number of moves and fairness. Report bootstrap confidence intervals by queue and shift.
* Promotion requires no protected-queue regression, zero hard-constraint violations in simulation and shadow replay, bounded inference latency, and an agreed improvement over the best baseline. Keep a policy kill switch and retain every decision for audit.
* Monitor feature/reward drift, forecast error, action-distribution drift, fallback rate, constraint failures, realized-vs-simulated reward and queue-level fairness. Alert the workforce manager; do not silently retrain or silently change business priorities.

### Delivery plan

1. **Foundation**: replace synthetic loaders with an adapter for interval aggregates; define versioned Pydantic schemas and persist decision/outcome logs. Keep all existing endpoints and tests working.
2. **Simulator and baselines**: migrate the current simulator to `WorkforceEnv`, add calibration reports, OR-Tools feasibility solver and a deterministic replay/evaluation harness. Require the RL candidate to beat both current baselines offline.
3. **Policy service**: add RLlib training jobs, MLflow registry, masked inference, guardrails and explicit fallback responses. Add `/workforce/policy/health` and `/workforce/policy/decision` behind feature flags; do not change `/workforce/routing` semantics until shadow results are accepted.
4. **Shadow and canary**: record recommendations for at least several representative weeks, review queue-level results, then canary one queue/shift with human approval and rollback.
5. **Controlled automation**: enable bounded auto-apply only for approved scenarios, with audit records, monitoring, kill switch and scheduled retraining.

The current evaluation suite is available at `GET /workforce/policy/evaluate`. It reports per-hour baseline score, RL score, improvement, move count, safety status, whether each scenario meets the fallback baseline, and an overall `promotionReady` flag. The current bootstrap policy is **not promotion-ready**: on the present real-derived seed it regresses in the technical-incident and queue-imbalance scenarios. Scenarios are derived from the ingested CC0 daily aggregates and are explicitly labelled as reconstructed stress cases: they are useful for policy testing, but do not replace native timestamped production intervals.

**Definition of done for the RL rework:** native real historical interval data is used (the current CC0 daily source is only a bootstrap proxy); simulator calibration is documented; RLlib policy beats both baselines on held-out real-day and stress scenarios; action masking and OR-Tools guards produce zero hard violations; shadow and canary metrics are observable; every decision is reproducible from its logged state, versions and seed; and the existing mock/HTTP gateway contract remains backward compatible.

## Method 5: breaks and shifts (`scheduling.py`)
* Each queue has **20 % more people on shift than desks needed** ("shrinkage") so that lunches can rotate. Everyone on a shift of 6 hours or more takes **one hour of lunch** starting at 11h, 12h, 13h or 14h.
* **Naive plan**: everybody at 12h (the busiest time: the queue empties). **Planned**: build the plan one advisor at a time at the hour that costs the fewest calls answered in time, then polish with a local search (move one lunch if that wins calls). The score charges a proportional penalty for every advisor short of the load, so the search cannot "sacrifice" a whole hour.
* **Overtime estimate**: what is still short of 80 % after the lunches, hour by hour, as advisors on overtime.
* Result today: worst hour per queue **0 % (naive, everyone at 12h) to 59 to 82 % (planned)**; day service level 82 % naive to 85 % planned; **10 overtime-hours** still needed.

## API (agents service)
| Endpoint | Input | Answer |
|---|---|---|
| `GET /workforce/forecast?queue=B` | queue `A` to `E` | one point per hour: `{hour, actual, forecast}` |
| `POST /workforce/simulate` | `queue`, `extraAdvisors` (-5 to 10), `from`, `to` (`HH:MM`) | before and after wait and service level, hour-by-hour `hours`, `recommendations`, `method` |
| `GET /workforce/routing` | none | the deterministic fallback routing plan: baseline and optimised service level, moves with explanations per hour, the simulation check, `method` |
| `GET /workforce/rl-routing` | none | shadow RL recommendations, masked and safety-checked moves, training metadata, and the unchanged fallback plan |
| `GET /workforce/policy/health` | none | policy readiness, mode, action count, training seed and hard constraints |
| `GET /workforce/policy/evaluate` | none | evaluates the RL policy against real-derived baseline, peak, low-volume, premium-spike, technical-incident and queue-imbalance scenarios |
| `GET /workforce/schedule` | none | the lunch plan per queue (naive vs planned), overtime, `method` |

## In the web app (`/workforce`, role `sana`)
* **Forecast vs actual** chart for a queue; **Load by hour** (a slider scrubs the day, each hour coloured calm, busy or overloaded against a 60 calls/hour capacity, with the estimated wait and service level).
* **What-if simulation** form (queue, extra advisors, from, to) and its result, with **"How this was computed"**: the hour-by-hour table and the method text.
* **Routing and allocation**: the deterministic fallback moves hour by hour with their explanations, the before/after per queue, "Apply the moves" (a demo action) and the simulation check. The RL shadow endpoint exposes the learned proposals separately until the UI is migrated.
* **Breaks and shifts**: lunches spread out vs everyone at noon, per queue, and the overtime needed.
* Every text has a **Listen** button.

## Explainability
No black box: every number comes with the formula and the hour-by-hour table. Every routing move states the service levels before and after for both queues; every recommendation states the calls, the advisors needed and the current level. A second method (the discrete-event simulation) checks the first.

## Tests (`services/agents/tests/test_agents.py`)
Erlang C against the textbook; the forecast has one point per hour and actuals only until now; a simulation is consistent with its hour-by-hour table; a window outside opening hours says so; input validation; routing keeps every advisor, respects skills and the protected level, never makes the weighted service level worse, and the independent simulation agrees; every eligible advisor gets exactly one lunch inside the shift and the planned lunches beat everybody at noon; the endpoints. Web and browser tests cover the page, the slider, the routing and the breaks sections.

## Honest limits
Synthetic history, advisors, skills and priorities. Erlang C assumes calls arrive randomly and nobody abandons; real centers have abandonment, retrials and skills-based routing inside queues. Routing is greedy: no guarantee of the optimum, and reinforcement learning is not implemented. Only a typical Wednesday is forecast; no holidays, campaigns or absences.

## Files
`services/agents/workforce.py`, `routing.py`, `rl_workforce.py`, `scheduling.py`, `app/views/workforce.njk`, `app/src/pages/pages.controller.ts` (workforce routes), `app/src/pages/charts.ts` (the SVG charts).
