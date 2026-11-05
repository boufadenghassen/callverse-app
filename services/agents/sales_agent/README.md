# Sales agent

Leila's agent: it spots what a customer needs, in the conversation or in their file, and ranks the offers that answer it, with the reasons in points. Everything about it lives in this folder; `../main.py` only routes to it.

## What it does
1. **Opportunity detection.** A local, multi-label NLP classifier reads what the *customer* says (not the advisor) and identifies needs such as travelling abroad, running out of data, wanting another plan, someone to add to the account, or thinking of leaving. It uses TF-IDF word and character features plus one-vs-rest logistic regression, so it can recognise wording variation instead of requiring an exact phrase. Each need keeps its quote and time; a need said twice is stronger; a denied need ("I'm not leaving") is deterministically excluded. The customer's file adds weaker needs (the reasons of their contacts, usage dropping).
2. **Offer recommendation.** For each offer that answers a need, the relevance (0 to 100) is the sum of named factors, each with its points and its reason in words: what the customer said (up to 50), fit with the contract (15; an offer the plan already covers, or the customer already owns, is set aside with the reason), customer value (up to 15), the moment (-20 to +10), the track record (-10 to +10). Nothing is hidden in a model: the page shows the factors and one counterfactual ("without the open ticket the relevance would be 46").
3. **Timing.** Do not sell to someone who is upset or has an open ticket: the offer is marked "wait: solve the problem first". A retention offer is the exception: it suits an upset, at-risk customer once the problem is acknowledged.
4. **What converts.** Every offer made is logged with its relevance, moment and need, then marked accepted or declined (`POST /sales/outcome`). The smoothed acceptance rate of an offer feeds its track record factor, and `GET /sales/analytics` shows conversion by offer, relevance, moment and need.

## Files
| File | Role |
|---|---|
| `engine.py` | Needs, factors, ranking, timing: `detect`, `recommend`, `opportunities` |
| `intent_model.py` | Trainable local multi-label classifier and confidence threshold |
| `training_examples.json` | Bootstrapping labelled utterances; replace with an approved export in deployment |
| `store.py` | SQLite log of offers and outcomes (`../data/sales.db`, git-ignored, `SALES_DB` to move it), simulated history, analytics |
| `tests/test_sales.py` | The agent's tests |
| `../knowledge/offers.json` | The invented offer catalogue, the need patterns, the plan upgrade path |
| `../knowledge/sales_profiles.json` | Invented sales facts about the five demo customers (tenure, usage trend, add-ons) |

## Endpoints (in `../main.py`)
`GET /sales/opportunities` (the contract's `Opportunity[]`, with extra fields: `customerId`, `offerId`, `price`, `factors`, `timing`, `counterfactual`, `alternatives`); `POST /sales/detect` `{customer_id?, turns}`; `POST /sales/outcome` `{customer_id?, offer_id, outcome, relevance, cue, need}`; `GET /sales/analytics`; `POST /sales/simulate` `{calls, share, min_relevance, good_moment_only}`. Offers also carry `acceptance`, `expected` and the customer `churn` (churn risk as a sum of named factors, the chance of a yes from similar offers in the history, what a yes is worth over 12 months). Details in `docs/agents/05-sales-agent.md`. The web app side: `app/src/pages/sales.controller.ts`, `app/views/sales.njk`.

## Training and deployment

The classifier trains locally when the service starts. It has no API key, cloud call, or customer-text egress. By default it uses `training_examples.json`, a small labelled bootstrap corpus used only to make the demo runnable. For a real deployment, export reviewed customer utterances as JSON and set:

```powershell
$env:SALES_TRAINING_DATA = "D:\approved-data\sales-labelled-utterances.json"
```

The export is an array of `{ "text": "...", "needs": ["travel", "data_short"] }` records and must contain at least 20 labelled utterances. Keep a held-out evaluation set and approve labels before training; do not train on raw customer transcripts without the appropriate consent and retention policy. The model returns needs over its confidence threshold, while eligibility, negation, timing, and outcome logging remain deterministic safeguards.

## Public telecom models

After downloading the public files to the ignored `services/agents/data/public/` folder, run:

```powershell
py -m sales_agent.public_models
```

This trains an IBM Telco churn model on the two fields the agent actually receives (tenure and monthly charge), saves it under ignored `data/models/`, and returns its held-out ROC-AUC. Its probability is added beside the transparent churn score when the artifact exists. It also trains an offline KDD Cup 2009 / Orange upsell benchmark. KDD fields are anonymised, so that model is deliberately not used to score or explain Callverse customers.

## Honest limits
* This is a real local ML classifier, but the checked-in bootstrap labels, offers, prices, plans, and customers are demo data. It becomes domain-accurate only after training on approved, representative labelled conversations.
* The history behind "which offers convert" starts SIMULATED (an offer is accepted more often when it is relevant and offered at a good moment, because that is how it was written), so the analytics initially show the loop works, not how real customers behave. Outcomes recorded from the page are real rows (`source = advisor`).
* Not built (ideation: perspective): purchase and churn propensity scores, commercial simulation of revenue.

Tests, from `services/agents`: `pytest -q sales_agent/tests`
