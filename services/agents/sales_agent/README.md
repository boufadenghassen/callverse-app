# Sales agent

Leila's agent: it spots what a customer needs, in the conversation or in their file, and ranks the offers that answer it, with the reasons in points. Everything about it lives in this folder; `../main.py` only routes to it.

## What it does
1. **Opportunity detection.** Phrase patterns on what the *customer* says (not the advisor) find needs such as travelling abroad, running out of data, wanting another plan, someone to add to the account, thinking of leaving. Each need keeps its quote and time; a need said twice is stronger; a denied need ("I'm not leaving") does not count. The customer's file adds weaker needs (the reasons of their contacts, usage dropping).
2. **Offer recommendation.** For each offer that answers a need, the relevance (0 to 100) is the sum of named factors, each with its points and its reason in words: what the customer said (up to 50), fit with the contract (15; an offer the plan already covers, or the customer already owns, is set aside with the reason), customer value (up to 15), the moment (-20 to +10), the track record (-10 to +10). Nothing is hidden in a model: the page shows the factors and one counterfactual ("without the open ticket the relevance would be 46").
3. **Timing.** Do not sell to someone who is upset or has an open ticket: the offer is marked "wait: solve the problem first". A retention offer is the exception: it suits an upset, at-risk customer once the problem is acknowledged.
4. **What converts.** Every offer made is logged with its relevance, moment and need, then marked accepted or declined (`POST /sales/outcome`). The smoothed acceptance rate of an offer feeds its track record factor, and `GET /sales/analytics` shows conversion by offer, relevance, moment and need.

## Files
| File | Role |
|---|---|
| `engine.py` | Needs, factors, ranking, timing: `detect`, `recommend`, `opportunities` |
| `store.py` | SQLite log of offers and outcomes (`../data/sales.db`, git-ignored, `SALES_DB` to move it), simulated history, analytics |
| `tests/test_sales.py` | The agent's tests |
| `../knowledge/offers.json` | The invented offer catalogue, the need patterns, the plan upgrade path |
| `../knowledge/sales_profiles.json` | Invented sales facts about the five demo customers (tenure, usage trend, add-ons) |

## Endpoints (in `../main.py`)
`GET /sales/opportunities` (the contract's `Opportunity[]`, with extra fields: `customerId`, `offerId`, `price`, `factors`, `timing`, `counterfactual`, `alternatives`); `POST /sales/detect` `{customer_id?, turns}`; `POST /sales/outcome` `{customer_id?, offer_id, outcome, relevance, cue, need}`; `GET /sales/analytics`. The web app side: `app/src/pages/sales.controller.ts`, `app/views/sales.njk`.

## Honest limits
* Not a language model: the needs come from phrase patterns, so a paraphrase can be missed and a loose phrase can be over-read ("I need to call my wife" also reads as a family need). The detector is where an LLM or an embedding model would go.
* The offers, prices, plans and customers are invented. The history behind "which offers convert" is SIMULATED (an offer is accepted more often when it is relevant and offered at a good moment, because that is how it was written), so the analytics show the loop works, not that real customers behave this way. Outcomes recorded from the page are real rows (`source = advisor`).
* Not built (ideation: perspective): purchase and churn propensity scores, commercial simulation of revenue.

Tests, from `services/agents`: `pytest -q sales_agent/tests`
