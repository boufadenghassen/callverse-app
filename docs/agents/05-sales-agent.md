# 5. Sales agent (Leila, sales)

## Purpose and persona
Leila Mansour, the sales manager, says *"The best upsell is the one that actually solves what the client just told me."* She is measured on conversion, not on the number of pitches, and wants real-time relevant offers during the call, visibility on the customer's profile and past interactions, timing cues for when an offer will land, and feedback on which offers convert and why. The ideation had four groups:

| Ideation group | Decision | Built |
|---|---|---|
| Opportunity detection (from the conversation) | prototype | **yes** |
| Offer recommendation (up-selling, customer-product match, relevance, personalised promotion) | prototype | **yes** (relevance score with its reasons, timing advice) |
| Propensity scores (purchase, churn, offer acceptance) | perspective | **yes, as readable scores**: churn risk (a sum of named factors) and the chance of a yes for each offer (from the history of similar offers); the purchase propensity is that chance of a yes |
| Commercial simulation (revenue per interaction, scenarios) | perspective | **yes, on the simulated history**: what a yes is worth, the expected value of each offer, and a replay of the history under a selling rule; no market or customer-growth model |

Plus two things the persona asked for: the "which offers convert" loop (**built**, on a simulated history) and **offers during the live call** (**built**: the advisor console shows the offer to keep in mind after every customer message).

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

### 7. Churn risk (`engine.churn_risk`)
A score from 0 to 100, a **sum of named factors** like the relevance, read from the customer's file and the conversation. Nothing is learned.

| Factor | Points | Rule |
|---|---|---|
| Starting point | +10 | every customer has some risk |
| Usage | +30 / +15 | usage down 30 % or more / 15 % or more in two months (file) |
| Talks about leaving | +25 / +20 | said in this conversation / contacted us about cancelling (file); a usage drop alone is counted once, above |
| Price | +10 | said in the conversation that it is too expensive |
| Open tickets | +8 each, at most +16 | the file |
| Passed around | +4 per transfer, at most +12 | the file |
| Mood | +15 under 40, +5 under 55, -5 from 65 | the latest mood |
| Years with us | -10 from 5 years, -5 from 2, +5 under 1 | the file |

High from 60, Medium from 30, Low below. With the five demo customers: Salma Hammami 75 (High), Walid Ferjani 64 (High), Yasmine Toumi 17, Mounir Sassi 10, Ines Kacem 0 (Low). With no customer file the conversation alone is read.

### 8. Chance of a yes, and what a yes is worth (`engine.acceptance`, `engine.expected`)
* **Chance of a yes** for an offer: the offer's own smoothed rate in the history, (accepted + 2) / (offered + 4), adjusted by what happened to **similar offers** (same offer, same relevance band, same moment). The similar cases count as five cases of the offer's own rate, so two similar cases move the figure a little and sixty move it a lot. Kept between 2 % and 95 %. The reason is shown in words ("6 similar offers in the history (relevance 70+, good moment): 3 accepted; this offer overall: 41 % of 24"). With an empty history there is no figure.
* **Worth** if the customer says yes, in TND of revenue booked over the next 12 months (invented prices, `values` in `offers.json`): for example Data Booster 9 x 12 = 108, Home Fiber 39 x 12 = 468, Roaming Pass 25 (one pass). Auto-pay counts 0 (it lowers late payments, not sales). **A retention offer is worth what it keeps minus what it gives**: the churn risk times a year of the customer's bill, minus 15 % of that year, assuming a yes keeps the customer. So for Salma Hammami (28 TND a month) the loyalty discount is worth 202 TND from her file alone (75 % risk: it keeps 252 TND and gives 50), and 286 TND once she also says she wants to cancel (risk 100); for a customer with a 10 % risk and a 42 TND bill it would be about -25 TND, because the discount would cost more than it keeps.
* **Expected value** = chance of a yes x worth.

### 9. Commercial simulation (`store.simulate`, `POST /sales/simulate`)
Replays the history of offers under a **selling rule**: a minimum relevance and "only at a good moment". The log holds the offers made when anyone could be offered anything, so it stands for the opportunities and a rule keeps some of them:
* opportunities = calls per month x the share of calls with a chance to offer (30 % by default);
* offers made = opportunities x the share of the log the rule keeps; yes = offers x the acceptance rate of the kept rows;
* revenue = opportunities x (the 12-month worth of the accepted kept rows / all rows).

On the untouched simulated history, 1,000 calls a month: *offer at every opportunity* 300 offers, 85 yes (28 %), 7,235 TND; *relevance 50 or more* 198 offers, 72 yes (37 %), 6,529 TND; *relevance 70 or more* 112 offers, 48 yes (42 %), 3,661 TND; *70 or more at a good moment* 89 offers, 46 yes (52 %), 3,474 TND. It shows the trade honestly: a stricter rule makes fewer offers, a higher yes rate and far fewer refusals, but earns less in total, because **refusals are not priced** (an annoyed customer, a longer call). That cost is not modelled.

### 10. Offers in the live call
In the advisor console, after each message from the simulated customer, the page sends the conversation so far (with the customer's mood) to `POST /advisor/live/offers`; the web app calls the same detection as the Sales page for the demo customer file (`YT-1042`) and shows at most two offers. The panel **Offer to keep in mind** shows the churn risk, the needs heard, the best offer with its relevance, the timing (*Wait: solve the problem first* or *Good moment to offer*), the chance of a yes, the worth and the reasons in points, and the buttons **Customer accepted / Declined** (recorded like on the Sales page, so the advisor feeds the track record). In demo mode (no real agents) the panel simply does not appear. The conversation is a plain list of turns, so an automated advisor can feed it the same way later.

## API (agents service)
| Endpoint | Input | Answer |
|---|---|---|
| `GET /sales/opportunities` | none | the contract's `Opportunity[]` (`customer, offer, relevance, reason`) plus `customerId, offerId, price, kind, pitch, need, factors[{name, points, why}], timing{cue, why}, counterfactual, alternatives[]` |
| `POST /sales/detect` | `customer_id` (optional), `turns` (1 to 100; each `speaker`, `text` 1 to 600 characters, optional `start`, `mood`) | `{customerId, customer, mood, signals[], offers[], skipped[]}`; unknown customer 404; bad body 422 |
| `POST /sales/outcome` | `customer_id` (optional), `offer_id`, `outcome` (accepted or declined), `relevance`, `cue`, `need` | `{recorded: true}`; unknown offer or customer 404 |
| `GET /sales/analytics` | none | totals, rates and the four conversion tables, `method` |
| `POST /sales/simulate` | `calls` (1 to 100,000, default 1,000), `share` (1 to 100 %, default 30), `min_relevance` (0 to 100), `good_moment_only` | `{calls, share, opportunities, history, simulated, policies[4], yours, method}`; each policy: `label, minRelevance, goodMomentOnly, offers, accepted, declined, rate, revenue, perCall`; out of range 422 |

New fields in the existing answers: every offer carries `acceptance` (`probability, similar, similarAccepted, basis`) and `expected` (`ifYes, chance, tnd, how`); `opportunities` entries and the `detect` answer carry `churn` (`score, level, factors[]`).

## In the web app (`/sales`, role `leila`)
* **Offer cards**: one per customer with an offer (the customer, the suggested offer and price, the relevance ring, the reason, the **timing** line), a **Why this offer** panel (every factor with its points, the counterfactual, the next best offers) and **Customer accepted** / **Declined** buttons that record the outcome.
* **Read a conversation**: pick a customer (or "Not on file"), paste or choose one of three samples (*Going abroad*, *Thinking of leaving*, *Family and data*), press **Find opportunities**: the needs found with their quotes, then the offers ranked with their factors and the same buttons; offers set aside are listed with the reason.
* **On every card and every offer found**: the **churn risk** (a coloured chip, with *Why this churn risk* listing its factors), the line *Chance of a yes 43 % · worth 108 TND over 12 months if yes · expected 46 TND* and, in *Why this offer*, the similar offers it rests on.
* **What a selling rule would earn**: calls per month, share with a chance to offer, minimum relevance and *Only at a good moment*; **Simulate** redraws a table with the four standard rules and the visitor's own rule.
* **Which offers convert**: four tables (by offer, relevance, moment, need) and "How this was computed".
* **Advisor console**: the live-call panel described above. The advisor role may also report an outcome (`POST /sales/outcome`).
* Demo mode keeps the two demo cards and hides the reader and the tables. The page says "Real agent, invented offers and customers" when the agent runs.

## Explainability
The whole score is a sum of named, signed, worded factors, so the screen answers "why this offer" and "what would change it". Needs show the customer's own words and the time. Offers that are not suggested say why. The track record states where it comes from and that it is simulated.

## Tests
Python (13): needs with quote and time, strength when said twice, denied needs, offers follow the need and respect the contract, relevance = sum of factors and the counterfactual really happens, the moment and the retention exception, the track record moves the ranking a little, the simulated history is created once and the analytics read it, the API validates its input; churn risk is a sum of factors and follows the customer, the chance of a yes is smoothed and comes from similar offers, what a yes is worth (a retention offer can lose money), the policy simulation trades volume for acceptance, the new figures travel through the API. Web (10): roles, demo mode refusals and guards, the page with the real agent's data, conversation cleaning and validation, outcome validation, the gateway's mapping of refusals, the new figures on the page, the simulation's validation, the live-call offers route (at most two offers, the mood kept only as a whole 0 to 100, roles), the advisor reporting an outcome. Browser (2): the whole flow against the real agent (cards, churn risk, chance of a yes, the conversation reader, the simulation), and the live-call panel with its outcome. Accessibility audit clean.

## Honest limits
Patterns, not a language model: a paraphrase can be missed and a loose phrase over-read ("I need to call my wife" also reads as a family need). Invented offers, prices, bills and customers. The conversion history is simulated, and it was written so that acceptance rises with relevance and a good moment, so the **chance of a yes and the simulation reproduce that rule**: they show the loop works, not how real customers behave. The churn risk is a hand-weighted sum (no model learned from real departures). A retention offer's worth assumes a yes keeps the customer. The simulation does not price refusals. **Not built**: a learned purchase or churn model, a market or growth simulation, A/B comparison of offers, profit (only revenue) per offer.

## Files
`services/agents/sales_agent/engine.py`, `store.py`, `tests/test_sales.py`, `README.md`; `services/agents/knowledge/offers.json` (offers, needs, values), `sales_profiles.json`; web: `app/src/pages/sales.controller.ts`, `live-call.controller.ts` (offers route), `app/views/sales.njk`, `advisor.njk` (offer panel), `app/client/app.ts` (reader, simulation, outcome buttons, live panel), `app/test/sales.spec.ts`.
