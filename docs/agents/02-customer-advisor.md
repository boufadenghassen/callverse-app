# 2. Customer advisor (Karim, the advisor)

## Purpose and persona
Karim Belhadj, the advisor, says *"I just need the right answer in one click, not five open tabs."* The agent reads what the customer says, finds the passage of the knowledge base that answers it, and suggests a sourced reply with the policy that applies. The ideation had four idea groups: understand the request, 360° customer view, knowledge and rules, guided actions.

## Status
**Real**, with these simplifications: the knowledge base is invented (12 passages), retrieval is TF-IDF (no language model), and "guided actions" is partial (a policy warning and an escalate button; no transfer recommender).

## How it works
### Retrieval of the answer (`suggest`)
1. The knowledge base `knowledge/base.json` has 12 passages, each with a `source` (for example "Billing policy §4.2"), a `title`, the `text` it is matched on, a ready-made `reply` and an optional `policy` warning. The topics: duplicate charge, how a refund is approved, roaming bundle not working abroad, compensation for a failed roaming bundle, cancellation and early termination fee, changing the plan, data limit does not match the plan, disputing an invoice, transfers and callbacks, empathy and customer history, SIM card replacement, payment methods and late payment.
2. The passages are turned into **TF-IDF vectors** (scikit-learn; one and two word sequences, sublinear term frequency, English stop words removed).
3. The customer's sentence is vectorised the same way and compared with every passage by **cosine similarity**. The three best passages are kept.
4. If the best score is under **0.08** the agent does not guess: it answers *"I could not find a reliable answer in the knowledge base for this. Please ask the customer to give more details, or escalate to a supervisor."* with no sources.
5. Otherwise the suggested text is the best passage's `reply`. (A customer's first name can be put in front, "Hello Yasmine.", when the caller passes it; the HTTP endpoint does not yet.)
6. `sources` lists the sources of every passage scoring at least 0.08; `evidence` lists them with their score and title.
7. The score is returned as `confidence`. It is a cosine similarity, **not a probability**, and the web pages no longer display it.

### Policy warning
If the customer's sentence mentions an amount in TND, dinars or DT above **50**, the warning says *"Refunds above 50 TND need supervisor approval (120 dinars was mentioned)."* Otherwise the matching passage's own `policy` text is used (for example the refund passage).

### Intent chips
Six intents are detected with word patterns (several can match): Billing, Roaming, Cancellation, Plan change, Data usage, Complaint. They show as chips on the customer card and feed the quality analyst (the call's intent) and the sales agent.

### Customer 360° (`knowledge/customers.json`)
Five invented customers, each with `id`, `name`, `profile`, `intents`, `contract`, `openTickets`, `transfers`, `mood`:

| Id | Name | Profile | Contract | Tickets | Mood |
|---|---|---|---|---|---|
| YT-1042 | Yasmine Toumi | Loyal customer, 6 years | Mobile Plus 40 GB | 1 | Impatient |
| MS-0007 | Mounir Sassi | New customer, 2 weeks | Starter 10 GB | 0 | Curious |
| IK-2210 | Ines Kacem | Premium customer, 3 years | Premium Unlimited | 0 | Calm |
| WF-3391 | Walid Ferjani | Unsatisfied customer, repeated contact | Mobile Plus 40 GB | 2 | Frustrated |
| SH-5520 | Salma Hammami | At-risk customer, usage dropping | Mobile Basic 20 GB | 1 | Angry |

## API (agents service)
| Endpoint | Input | Answer |
|---|---|---|
| `POST /advisor/suggest` | `customer_id` (two capital letters, a dash, four digits), `query` (3 to 500 characters) | `{text, sources[], policyWarning, confidence, intents[], evidence[{source, score, excerpt}]}` |
| `GET /advisor/customers/{id}` | id as above | the customer's record; unknown id: 404; badly formed id: 422 |

## In the web app (`/advisor`, role `karim`)
* **Customer 360° card**: name, profile, intent chips, contract, open tickets and transfers, mood. The customer is chosen with `?customer=ID` (default YT-1042) and the search with `?q=` (3 to 200 characters, control characters removed; default "double charge on monthly bill"); anything else is refused with a 400.
* **Knowledge assistant**: a search box; the suggested answer with its **Sources**, the list of passages it comes from, and the policy warning (yellow). **Listen** reads the answer aloud ([07-voice.md](07-voice.md)). Buttons *Use answer*, *Edit*, *Escalate* show a confirmation (nothing is sent anywhere).
* **Live call**: after every message of the simulated customer ([01-customer-simulator.md](01-customer-simulator.md)) the agent suggests the next answer from the call's topic (the customer's opening line) plus what she just said, so a short "okay" keeps the suggestion on topic; each suggestion comes with its sources and intents; the advisor can use it, type (1 to 300 characters), or record a voice note.
* Demo mode serves the same screens with fixed answers.

## Explainability
Nothing the agent says comes from nowhere: each answer is one passage's text, its source is shown and the other candidate passages are listed as evidence. The policy warning states the rule (and the amount that triggered it). The score of the match exists in the data but is not shown to users.

## Tests
`services/agents/tests/test_agents.py`: the right passage is chosen and cited; big refunds are flagged; "I don't know" when nothing matches; intents; the customer lookup (known, unknown 404, malformed 422). Web: advisor page, live-call routes and the browser tests.

## Honest limits
Twelve invented passages; TF-IDF cannot understand paraphrases ("I paid two times" works, "my money left twice" may not); only the best passage's reply is used, never a mix; no memory of the conversation beyond the last customer message; the knowledge base is where a vector search over the real FAQ (and later an LLM that must cite it) would go.

## Files
`services/agents/advisor.py`, `services/agents/knowledge/base.json`, `knowledge/customers.json`, `app/views/advisor.njk`, `app/src/pages/pages.controller.ts` (advisor route), `app/src/pages/live-call.controller.ts`.
