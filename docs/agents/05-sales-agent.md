# 5. Sales agent (Leila, sales)

## Purpose and persona
Leila Mansour, the sales manager, says *"The best upsell is the one that actually solves what the client just told me."* She is measured on conversion, not on the number of pitches, and wants real-time relevant offers during the call, visibility on the customer's profile and past interactions, timing cues for when an offer will land, and feedback on which offers convert and why. The ideation had four groups:

| Ideation group | Decision | Built |
|---|---|---|
| Opportunity detection (from the conversation) | prototype | **yes** |
| Offer recommendation (up-selling, customer-product match, relevance, personalised promotion) | prototype | **yes** (relevance score with its reasons, timing advice) |
| Propensity scores (purchase, churn, offer acceptance) | perspective | no (kept for later) |
| Commercial simulation (revenue per interaction, scenarios) | perspective | no (kept for later) |

Plus the "which offers convert" loop asked by the persona's needs: **built**, on a simulated history.

## Status
**Real.** The needs are found by phrase patterns (no language model); **the offers, prices, plans and customers are invented; the history behind "which offers convert" is simulated.** Code: `services/agents/sales_agent/` (own README there).

## How it works
### 1. Finding needs (`engine.conversation_needs`, `file_needs`)
Ten needs, each with a pattern list (in `knowledge/offers.json`):

| Need | Reads as |
|---|---|
| Travelling abroad | abroad, trip, flight, holiday, "going to Paris/Italy/..." |
| Running out of data | "ran out of data", "not enough data", "need more data", slow internet, streaming, videos |
| Wants a different plan | "change / upgrade / switch my plan", "bigger plan", "plan change" |
| Someone to add to the account | "my wife / husband / son / kids", "second line", "add a number" |
| Internet at home | wifi, router, fibre, "work from home" |
| Thinking of leaving | cancel, leave, "another operator", competitor, "close my account" |
| Finds it too expensive | expensive, price, cheaper, "bill is too high", discount |
| Payment trouble | late fee, "forgot to pay", direct debit, bank card |
| Wants priority service | "waited too long", dedicated advisor, VIP, account manager |
| Phone problem or upgrade | "new phone", battery, "screen is broken" |
| Calls to people abroad | "calling my family abroad", international calls |

* Only the **customer's** sentences are read, sentence by sentence. Each need keeps its **first quote and its time**; a need said in several replies is stronger: strength = 0.7, plus 0.15 per extra reply, at most 1.
* **Denials do not count**: "I'm not leaving", "I don't want to cancel" are skipped for the needs that can be denied (leaving, travel, device, family, priority service).
* **The customer's file** adds weaker needs: the reasons of past contacts (Plan change 0.5, Data usage 0.5, Roaming 0.6, Cancellation 0.8, Billing 0.3) and **usage down 30 % or more in two months** (reads as "thinking of leaving", at least 0.6). A need said aloud wins over the same need from the file.
* The customer's **mood**: the mood given with her last reply, else guessed from her words (negative words 30, positive 65), else from the file (Calm 70, Curious 65, Impatient 45, Frustrated 30, Angry 20).

### 2. The offers (`knowledge/offers.json`, invented, prices in TND)
Roaming Pass 5 GB (25 per 7 days), Data Booster +20 GB (9 per month), Plan upgrade (to the next plan up, from 8 more per month), Family line add-on (12), Home Fiber 100 Mbps (39), Loyalty discount -15 % for 12 months (retention; needs a year of tenure), Auto-pay discount (-3), Premium Care line (10), Device upgrade plan (from 29), International calls pack (7). Each offer says which needs it answers (a weight 0 to 1), the plans that already cover it (Premium Unlimited already covers roaming, data, international calls, a plan upgrade and priority care, so a Premium customer is never offered them and the page shows each offer set aside with that reason), and a pitch. The upgrade path is Starter 10 GB, Mobile Basic 20 GB, Mobile Plus 40 GB, Premium Unlimited.

### 3. The relevance score = a sum of named factors (0 to 100)
| Factor | Points | Rule |
|---|---|---|
| **What the customer said** (or what the file says) | up to 50 | 50 x min(1, best need strength x link + 0.25 x the others) |
| **Fit with the contract** | +15 | the offer is not already covered or owned, and the tenure condition holds |
| **Customer value** | up to 15 | 6 years with us +10, 2 years +5, premium plan +5; a retention offer for a customer whose usage fell 30 % or more +15 |
| **The moment** | -20 to +10 | mood under 40: -20 (solve the problem before selling), except a retention offer +5 (suits an upset customer after acknowledging the problem); an open ticket -10; mood 60 or more +10; else 0 |
| **Track record** | -10 to +10 | 20 x (smoothed acceptance rate - 0.5) from the log of past outcomes: (accepted + 2) / (offered + 4) |

Each factor carries its reason in words. The **counterfactual** states the worst negative factor: *"Without 'The moment' (1 open ticket: solve it first), the relevance would be 46."*

### 4. Timing advice
`now` (good moment, or a retention offer for an upset customer) or `after_resolution` ("Wait: solve the problem first") when the moment factor is negative.

### 5. Detecting a conversation (`detect`)
Input: a conversation (and optionally a customer id). Output: the **signals** (need, label, quote, time, how many replies, strength, source conversation or file), the **ranked offers** (top 4) with factors, timing and counterfactual, the **offers set aside** with the reason, and the mood read. `opportunities()` does the same for each customer on file with no conversation: the best offer for each of the five customers today.

### 6. What converts (`store.py`)
Every offer made is logged (`offers_log`: date, customer, offer, relevance, timing, need, outcome accepted or declined, source) in **SQLite** (`services/agents/data/sales.db`, git-ignored). Outcomes come from the **Customer accepted / Declined** buttons (source `advisor`). An empty store is filled with **240 simulated offers** over eight weeks (deterministic); in the simulation an offer is accepted more often when it is relevant and made at a good moment, because that is how it was written. The analytics (`GET /sales/analytics`) give conversion by offer, by relevance band (70 or more, 50 to 69, under 50), by moment and by need.

## API (agents service)
| Endpoint | Input | Answer |
|---|---|---|
| `GET /sales/opportunities` | none | the contract's `Opportunity[]` (`customer, offer, relevance, reason`) plus `customerId, offerId, price, kind, pitch, need, factors[{name, points, why}], timing{cue, why}, counterfactual, alternatives[]` |
| `POST /sales/detect` | `customer_id` (optional), `turns` (1 to 100; each `speaker`, `text` 1 to 600 characters, optional `start`, `mood`) | `{customerId, customer, mood, signals[], offers[], skipped[]}`; unknown customer 404; bad body 422 |
| `POST /sales/outcome` | `customer_id` (optional), `offer_id`, `outcome` (accepted or declined), `relevance`, `cue`, `need` | `{recorded: true}`; unknown offer or customer 404 |
| `GET /sales/analytics` | none | totals, rates and the four conversion tables, `method` |

## In the web app (`/sales`, role `leila`)
* **Offer cards**: one per customer with an offer (the customer, the suggested offer and price, the relevance ring, the reason, the **timing** line), a **Why this offer** panel (every factor with its points, the counterfactual, the next best offers) and **Customer accepted** / **Declined** buttons that record the outcome.
* **Read a conversation**: pick a customer (or "Not on file"), paste or choose one of three samples (*Going abroad*, *Thinking of leaving*, *Family and data*), press **Find opportunities**: the needs found with their quotes, then the offers ranked with their factors and the same buttons; offers set aside are listed with the reason.
* **Which offers convert**: four tables (by offer, relevance, moment, need) and "How this was computed".
* Demo mode keeps the two demo cards and hides the reader and the tables. The page says "Real agent, invented offers and customers" when the agent runs.

## Explainability
The whole score is a sum of named, signed, worded factors, so the screen answers "why this offer" and "what would change it". Needs show the customer's own words and the time. Offers that are not suggested say why. The track record states where it comes from and that it is simulated.

## Tests
Python (8): needs with quote and time, strength when said twice, denied needs, offers follow the need and respect the contract, relevance = sum of factors and the counterfactual really happens, the moment and the retention exception, the track record moves the ranking a little, the simulated history is created once and the analytics read it, the API validates its input. Web (6): roles, demo mode refusals and guards, the page with the real agent's data, conversation cleaning and validation, outcome validation, the gateway's mapping of refusals. Browser (1): the whole flow against the real agent. Accessibility audit clean.

## Honest limits
Patterns, not a language model: a paraphrase can be missed and a loose phrase over-read ("I need to call my wife" also reads as a family need). Invented offers, prices and customers. The conversion history is simulated, so the analytics show the loop works, not how real customers behave. **Not built**: purchase and churn propensity, commercial simulation, linking an offer to the live call in the advisor console, A/B comparison of offers.

## Files
`services/agents/sales_agent/engine.py`, `store.py`, `tests/test_sales.py`, `README.md`; `services/agents/knowledge/offers.json`, `sales_profiles.json`; web: `app/src/pages/sales.controller.ts`, `app/views/sales.njk`, `app/client/app.ts` (reader and outcome buttons), `app/test/sales.spec.ts`.
