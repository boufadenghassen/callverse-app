# 4. Quality analyst (Nour, quality)

## Purpose and persona
Nour Chaabane, the quality analyst, says *"I can only listen to a fraction of calls, what about the rest?"* She needs consistent analysis of every call, objective and explainable criteria, feedback close to the call, and dashboards that find patterns. The agent scores a call, says exactly where every lost point came from, and turns reviews into coaching and team analytics. The ideation had four groups: scoring grid, error detection, coaching (tagged **XAI**), quality analytics. All four are built; this is the most complete agent. Its code is one package, `services/agents/quality_analyst/` (its own short README is there too).

## Status
**Real, rule based, explainable.** It is **not** an LLM judge: an LLM would replace the detectors in `engine.find_issues`, not the structure. The 84-call history behind the analytics is **simulated** (scored by the real engine); the accuracy is measured on calls we wrote and labelled.

## The score
A call is a list of turns `{speaker, text, start, end, mood?, emotion?}`. Missing times are estimated (1.5 s + length / 14 per turn); a missing customer mood comes from a small word list (and the review then says `moodSource: "text"`; the mood comes from the emotion model for recordings and from the simulator for live calls).

### Five criteria, each out of 10, with weights
| Criterion | Weight |
|---|---|
| Accuracy | 25 % |
| Compliance | 25 % |
| Communication | 20 % |
| Resolution | 20 % |
| Customer sentiment | 10 % |

Each rule that fires **costs points in one criterion** (a criterion never goes below 0). The overall score is `round(100 x sum(weight x criterion / 10))`.

### The 18 rules
Every finding records the **turn, the time, the quote, the points, the reason, the fix that would have avoided it and the cause** (process skipped, knowledge gap, soft skills, tools).

| Rule | Criterion | Points | What triggers it |
|---|---|---|---|
| `promise_before_check` | Compliance | 5 | the advisor promises a refund before any turn that checks the policy |
| `refund_over_limit` | Compliance | 4 | an amount above 50 TND is offered with an action and no mention of approval |
| `no_identity_check` | Compliance | 3 | an action on the account (refund, cancellation, SIM...) before the identity is verified (a question "can I..." or a policy check does not count) |
| `no_retention_offer` | Compliance | 2 | the customer wants to cancel and the advisor processes it before offering a plan review |
| `wrong_fact` | Accuracy | 4 | the advisor states a fact the knowledge base contradicts (five checked facts: dispute answered in 5 working days; service restored within 1 hour of payment; a plan change takes effect next billing cycle; a refund appears on the next statement; a replacement SIM keeps the number); at most 2 per call |
| `no_grounded_answer` | Accuracy | 3 | none of the advisor's turns resembles the knowledge-base passage that answers the customer's problem (TF-IDF cosine below 0.10 while a passage matches the question) |
| `overpromise` | Accuracy | 2 | an absolute guarantee ("I guarantee", "100 %", "never happen again"), unless hedged |
| `no_empathy` | Communication | 3 | the customer starts upset (mood under 45 or an angry, sad, fearful or disgusted voice) and neither of the first two advisor replies acknowledges it |
| `jargon` | Communication | 1 | technical terms (APN, provisioning, MSISDN, IMSI, CDR, backend, tier 2, CRM, IVR...); at most 2 |
| `ask_repeat` | Communication | 3 | asking the customer to repeat or retell; at most 2 |
| `transfer` | Communication | 2 | a transfer without passing the history or staying on the line; at most 2 |
| `no_greeting` | Communication | 1 | the first advisor words are not a greeting |
| `no_follow_up` | Resolution | 3 | no written confirmation, ticket number or follow-up |
| `unresolved` | Resolution | 4 | the customer's last mood is under 40 and nothing was agreed |
| `hang_up` | Resolution | 2 | the customer hangs up (outcome or "goodbye / I'm done" with a low mood) |
| `no_closing` | Resolution | 1 | the last advisor turn is not a closing question or thanks |
| `mood_drop` | Customer sentiment | 2 | the customer's mood falls 15 points or more right after an advisor reply (at most 2) |
| `low_mood_end` | Customer sentiment | `round((70 - mood) / 10)` | the customer leaves in a mood under 70 |

Seven **strengths** are also recorded: greeting, identity verified, empathy, policy checked before promising, written follow-up, closing, customer's mood rose by 15 or more.

### How a move is detected (`turn_flags`)
Each advisor sentence is examined whole and clause by clause. First **phrase patterns** (the customer simulator's patterns, widened with phrasings met in real advice: "bear with me", "money back today", "I'll text you"...). Then a **semantic second opinion**. Then **guards**: a denied promise, transfer, repeat or follow-up ("no need to transfer you") does not count; a promise inside a condition ("once it is approved") does not count; a guarantee that is hedged ("I hope", "might") does not count; a denial only cancels what it belongs to ("I will refund you right away, and I guarantee it will not happen again" is still a promise).

### The semantic second opinion (`semantic.py`)
A small sentence-embedding model (**all-MiniLM-L6-v2**, 22 million parameters, offline from the Hugging Face cache) embeds each sentence and compares it with 4 to 9 prototype sentences per move (empathy, check policy, promise, follow-up, ask repeat, transfer, greeting, closing, guarantee, identity). A move is detected when the cosine similarity reaches that move's threshold: 0.60 by default, **tuned on the development calls only**: check policy 0.45, follow-up 0.55, transfer 0.70. Without the model (for instance in CI) the analyst silently uses the patterns only (`QUALITY_SEMANTIC=0` forces that).

## Explainability (XAI): three mechanisms
The ideation tagged *Coaching: recommendations, strengths, weaknesses* as **XAI** and asked for "overall score and reasons".
1. **Evidence per lost point**: turn, quote, exact time and rule; the review page links each pin of the call timeline to its criterion row.
2. **Counterfactual coaching**, computed by really removing a finding: *"If a supervisor's approval had been asked for (at 00:19), compliance would rise from 6 to 10 and the overall score by +10."*
3. **What moved this score** (`engine.explained`): the answer to *"what did the advisor say that lowered the score, and what protected it?"*, as exact what-ifs.
   * A finding's `effect` is minus what the overall score gains when that finding is left out ("offered 120 dinars without approval": **-10**).
   * A strength's `effect` is what the call would have lost had the advisor not made that move (the sentences that make it are taken out of the reply, the rest kept): the mistakes it protected the call from, from a fixed map (`PREVENTS`): checking the policy protects against `promise_before_check`, identity against `no_identity_check`, empathy against `no_empathy`, greeting, follow-up and closing against their own rules. ("Checked the policy before promising": **+12**, "without it, the refund promise would have been flagged".) A strength with nothing at stake shows 0 and says so.
   * Effects are **not additive** (a criterion stops at 0, so two mistakes in it can share the same points); a finding that changes nothing on its own is marked `floored`, with the reason. The page says so.
4. **Reviewer dispute**: Nour marks a finding *Correct* or *Not an error*; a disputed finding stops counting, the scores, counterfactual and effects are recomputed, and the team view shows the agreement rate.

The explanation is worked out when a review is shown, never for the analytics; reviews stored before it existed get it on read.

## Three ways in
1. **A transcript through the API** (`POST /quality/review`).
2. **A live call** from the advisor console (`Send to quality review` after a call with the simulated customer; `POST /quality/review-call`).
3. **A two-channel recording** (advisor on the left, customer on the right; `POST /quality/review-audio?advisor=...`, up to 10 MB and the first 5 minutes): each channel is cut at silences (energy-based voice detection), each stretch is transcribed by Whisper with its time ([07-voice.md](07-voice.md)), sentences of the same speaker closer than 1.5 s are merged, and every customer sentence goes through the **emotion model** ([08-emotion-model.md](08-emotion-model.md)) to get the mood and emotion. A mono recording is refused with a clear message. A two-channel **sample call** (with mistakes on purpose, spoken by the neural voices) can be downloaded and uploaded to try the feature.

## Storage and analytics
* **SQLite** (`services/agents/data/quality.db`, git-ignored): tables `calls` (id, advisor, source, date, intent, overall, the whole review as JSON) and `feedback` (call, rule, turn, verdict, who, when). Call ids start at `CALL-3300`.
* **The simulated history**: an empty store is filled with **84 calls**: six advisors x 14 calls over eight weeks, deterministic. Each advisor has habits: Karim B. average; Hela M. very good; Sami R. improving over time; Rania K. weak on identity checks and policy checks; Mehdi T. declining; Ines F. warm but often wrong on facts and full of jargon. What advisors say is written from phrase banks; the customer's answers and mood come from the simulator; **every call is scored by the real engine**. So the analytics are computed, but they find habits that were programmed in: a sanity test of the engine, not evidence about real people.
* **Analytics** (`GET /quality/analytics`): team average and 8-week trend, average per criterion, most frequent errors, **root causes** (process skipped, knowledge gap, soft skills, tools), average by call intent; per advisor: average, difference from the team, weakest and strongest criterion, weekly trend, top errors and a **coaching plan** (the tip for each frequent error and a training scenario to practise it). The agreement rate of the reviewers and the most disputed rules.

## Measured accuracy (`evaluation.py`, `eval_cases*.py`)
* **213 hand-labelled calls** written by us in natural words (not the phrase banks of the simulated history), each saying which rules a careful human would say fire and which must stay silent. Split by id: **122 development** (where thresholds and phrase lists are tuned) and **91 held-out test** (never used for tuning).
* The journey, kept honest in the page: first measure on 72 development calls, keyword rules only, F1 84 %; first measure on 44 harder unseen calls, F1 75 % (keywords) and 81 % (with the semantic opinion); those misses were used to widen the phrase lists in general ways; **final measure on the 91 held-out test calls: precision 98 %, recall 100 %, F1 99 %** (keywords alone 98 %), development F1 98 %. Tests keep these above 95 %.
* Limits stated on the page: calls written by us, short, our own labels; a few calls move a rule's recall by 10 points; real calls will be harder (Arabic, French, noise, long calls); mood rules are checked on given moods.

## The human-agreement study (`quality_analyst/labelling/`)
To replace "our labels" by independent ones: `make_sheet.py` builds a **blind labelling sheet** (a single HTML page, 50 calls: 30 short held-out cases covering every rule and 20 simulated history calls spread from worst to best; 18 yes/no questions per call with plain definitions and the company facts), plus an `answer-key.json` kept away from labellers. Two people label alone and send a `labels-<name>.json`; `agreement.py` reports agreement between the two (percent and Cohen's kappa, per rule), the analyst against them (precision, recall, F1) and the calls where they differ. **Status: the sheet is ready and tested; the labels have not come back yet.**

## API (agents service)
`POST /quality/review` (`advisor`, `turns`: 1 to 200, each 1 to 1000 characters), `POST /quality/review-call` (`callId`, `advisor`), `POST /quality/review-audio?advisor=Name` (raw two-channel audio, up to 10 MB), `POST /quality/feedback` (`callId`, `rule`, `turn`, `verdict` agree, disagree or clear, `by`), `GET /quality/reviews` (`limit`, `advisor`, `rule`, `below`), `GET /quality/reviews/{id}`, `GET /quality/analytics`, `GET /quality/evaluation`, `GET /quality/sample-call.wav`. A review contains: `callId, advisor, overall, criteria[{name, score, max, evidence, timestamp}], counterfactual, source, date, durationSec, intent, moodSource, errors[], strengths[], coaching[], turns[] (with flags), moodCurve, drivers{hurt[], helped[]}` (and `adjusted, originalOverall` after disputes).

## In the web app (`/quality`, role `nour`; recordings reviewed on `/call-review`)
* **Team analytics**: averages, trend, frequent errors, root causes, a table of advisors with a sparkline and a coaching plan; the reviewers' agreement.
* **Review a call**: upload a recording (or download the sample call first).
* **Filters**: by advisor, by error (rule) and by score (below 70 or 50).
* **A review card**: header with the call and the score; the **call timeline** (pins = scored moments, sized by points lost, linked to the criterion rows) and the **customer's mood curve** (with its source); the criteria table with evidence and time; the **coaching hint** (with Listen); **What moved this score** (two columns); the list of reasons points were lost with *Correct* / *Not an error* buttons; "Done well" chips; coaching for the call; the full **transcript** with red and green marks on each reply.
* **Accuracy section**: precision, recall and F1 per rule on the development and test calls, with the known mistakes and the journey text.
* Print styles for the reviews.

## Tests (61 Python tests for the package, plus web and browser)
`tests/test_quality.py` (22: a good call scores full marks, a bad call loses points at the right moments, each rule fires only when it should, the counterfactual is exact, missing times and moods are filled in, a call without advisor turns is a failure not a crash, the simulated history is deterministic, HTTP reviews and refusals, a live call sent to quality, the two-channel recording and its refusals, the accuracy on calls never tuned on, the keyword rules alone, denied and conditional moves, at least three labelled calls per rule, the evaluation endpoint, reviewer disputes and agreement per rule, filters), `tests/test_drivers.py` (7: effects equal real re-scores, strengths as real what-ifs, floors, disputes, the call is never changed, old stored reviews), `tests/test_labelling.py` (3: the sheet is blind and complete, the agreement maths), `tests/test_robustness.py` (29: odd texts, huge calls, bad filters never crash; a fuzz run of 300 random calls found no crash). Web: `quality.spec.ts` (9); browser: 7 quality tests plus assertions on the explanation panel; axe audit clean.

## Honest limits
Rule based: a paraphrase can be missed (the semantic opinion helps, not perfectly); "I can see the duplicate..." is read as empathy (the empathy pattern is inherited from the customer simulator); simulated history; accuracy measured on our own calls; English only (Whisper `base.en`); a call needs two channels (a diarisation step would be needed for mono); the emotion service must run for audio moods.

## Files
`quality_analyst/engine.py` (rules, scoring, counterfactual, `explained`), `semantic.py`, `store.py`, `seed.py`, `audio.py`, `evaluation.py`, `eval_cases.py`, `eval_cases2.py`, `eval_cases3.py`, `labelling/` (`make_sheet.py`, `agreement.py`, `template.html`), `tests/`; web: `app/src/pages/quality.controller.ts`, `app/views/quality.njk`, `app/src/pages/charts.ts`, `app/client/app.ts` (verdicts, upload).
