# 3. Workforce manager (Sana, workforce)

## Purpose and persona
Sana Gharbi, the workforce manager, says *"I need to see problems before they happen, not after."* The agent forecasts the calls of a queue, tells how many advisors a queue needs, lets her **simulate a decision before applying it**, suggests which advisor should work which queue, and plans lunches. The ideation (agent name: *Workforce Manager Agent (RL)*) had four groups: forecast and monitor, routing and allocation, scheduling and staffing, risk and emergencies.

| Ideation group | Decision | Built |
|---|---|---|
| Forecast and monitor | production | **yes**: seasonal forecast, hour-by-hour load, waiting time and service level |
| Routing and allocation (RL) | production | **yes, as a local search, not reinforcement learning** (see below) |
| Scheduling and staffing | prototype | **yes**: what-if simulation, lunch plan, overtime estimate |
| Risk and emergencies | perspective | no (kept for later) |

## Status
**Real.** All three methods are explainable and checked by tests. **The call history, the advisors, their skills, the priorities and today's volumes are SYNTHETIC**; `workforce.load_history()` is the one function to replace with real call logs.

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

## Method 4: routing and allocation (`routing.py`)
*Which advisor should work which queue for the rest of the day.* **It is a local search on the Erlang C numbers, not reinforcement learning.** RL needs a calibrated simulator and real call logs and would have to be judged against this method, so it is kept for later.
* **Advisor pool**: 31 synthetic advisors (named by queue and number, for example `C02`); every second advisor is cross-skilled. Cross skills: A can also serve B; B: A; C: D and A; D: C and E; E: D.
* **Objective**: the priority-weighted number of calls answered within 20 s, sum over queues of priority x calls x service level. Priorities: A 1.0, B 1.3 (premium, counts 30 % more), C 0.9, D 1.0, E 0.8.
* **Search**: for each remaining hour, start from today's roster, and repeatedly make the **single move** of a cross-skilled advisor to another queue that raises the objective most, at most 6 moves per hour, each move having to win at least 0.05 weighted calls. A **guard** protects the donor queue: it may not fall below 65 % service (or below what it has now if it is already lower).
* **Explanation of every move**: for example *"Move C02 (skills C, D, A) from queue C to queue A at 14h: queue A goes from 47% to 71% within 20 s, queue C from 87% to 67%."*
* **Independent check**: a discrete-event simulation (Poisson arrivals, exponential handling times, first come first served, 60 repetitions, the first hour of each run discarded) re-measures the gain without using the formula. Result today: **3 moves, 68 % to 72 % by the formula, 70 % to 74 % in the simulation.**

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
| `GET /workforce/routing` | none | the routing plan: baseline and optimised service level, moves with explanations per hour, the simulation check, `method` |
| `GET /workforce/schedule` | none | the lunch plan per queue (naive vs planned), overtime, `method` |

## In the web app (`/workforce`, role `sana`)
* **Forecast vs actual** chart for a queue; **Load by hour** (a slider scrubs the day, each hour coloured calm, busy or overloaded against a 60 calls/hour capacity, with the estimated wait and service level).
* **What-if simulation** form (queue, extra advisors, from, to) and its result, with **"How this was computed"**: the hour-by-hour table and the method text.
* **Routing and allocation**: the moves hour by hour with their explanations, the before/after per queue, "Apply the moves" (a demo action) and the simulation check.
* **Breaks and shifts**: lunches spread out vs everyone at noon, per queue, and the overtime needed.
* Every text has a **Listen** button.

## Explainability
No black box: every number comes with the formula and the hour-by-hour table. Every routing move states the service levels before and after for both queues; every recommendation states the calls, the advisors needed and the current level. A second method (the discrete-event simulation) checks the first.

## Tests (`services/agents/tests/test_agents.py`)
Erlang C against the textbook; the forecast has one point per hour and actuals only until now; a simulation is consistent with its hour-by-hour table; a window outside opening hours says so; input validation; routing keeps every advisor, respects skills and the protected level, never makes the weighted service level worse, and the independent simulation agrees; every eligible advisor gets exactly one lunch inside the shift and the planned lunches beat everybody at noon; the endpoints. Web and browser tests cover the page, the slider, the routing and the breaks sections.

## Honest limits
Synthetic history, advisors, skills and priorities. Erlang C assumes calls arrive randomly and nobody abandons; real centers have abandonment, retrials and skills-based routing inside queues. Routing is greedy: no guarantee of the optimum, and reinforcement learning is not implemented. Only a typical Wednesday is forecast; no holidays, campaigns or absences.

## Files
`services/agents/workforce.py`, `routing.py`, `scheduling.py`, `app/views/workforce.njk`, `app/src/pages/pages.controller.ts` (workforce routes), `app/src/pages/charts.ts` (the SVG charts).
