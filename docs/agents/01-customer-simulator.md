# 1. Customer simulator (Yasmine, the client)

## Purpose and persona
Yasmine Toumi, the client, says *"I don't want to explain my problem five times, just fix it."* The simulator reproduces customers as varied and demanding as real ones, so advisors can practise and the other agents (advisor, quality analyst) have a customer to talk to. The ideation listed four idea groups for it: persona engine, emotional dynamics, context and memory, outcome signals. All four are built.

## Status
**Real.** The rules run in Python (`services/agents/customer.py`) and, in an identical TypeScript version, in the web app (`app/src/pages/client-simulator.ts`, `customer-llm.ts`). The two are kept in step by a test (below). The customer's *words* are written by rules: no language model.

## How it works
A call is the list of **moves** the advisor made. The state of the call (mood, patience, effort, whether it ended) is *replayed* from those moves every time, so the same moves always give the same call.

### 1. Reading the advisor (`read_advisor`)
What the advisor said, and how it sounded, becomes one of eight moves. **How it was said comes first** (a raised voice or rude words), then the first pattern that matches wins; specific actions come before the polite phrases that accompany them:

| Order | Move | Reads as (examples of what matches) |
|---|---|---|
| 0 | `RUDE` | a **raised voice** (the emotion model heard anger or disgust in a voice note and its mood is 30 or lower), **insults** (stupid, idiot, "shut up", "what the hell", swearing...), **shouting in writing** (three or more words in capitals in a row, or three or more exclamation marks) |
| 1 | `TRANSFER` | "let me transfer you", "put you through", "another team/colleague", "the billing team" |
| 2 | `ASK_REPEAT` | "could you repeat", "explain it again", "from the start", "what was your problem" |
| 3 | `PROMISE` | "I promise", "I guarantee", "I'll refund/credit/waive", "refund you right away", "consider it done" |
| 4 | `CHECK_POLICY` | check, verify, review, look into... (within 40 characters of) policy, procedure, rules, approval, eligibility, terms |
| 5 | `FOLLOW_UP` | "in writing", "by email", "send you a confirmation", "follow up", "call you back", "reference number" |
| 6 | `EMPATHY` | sorry, apologise, "I understand", "I can see/imagine", "that must be", frustrating, "thank you for your patience" |
| - | `OTHER` | anything else; she still answers what was said (see 5) |

### 2. Personas (5), difficulty (3), intent (3)
Each persona has a starting **mood** and **patience** (0 to 100) and three sensitivities (0 to 1): how much *repeating* hurts, how much *empathy* helps, how much *speed* matters.

| Persona | Label | Mood | Patience | Repeat | Empathy | Speed |
|---|---|---|---|---|---|---|
| `IMPATIENT` | Impatient but fair | 55 | 65 | 0.9 | 0.5 | 0.9 |
| `ANXIOUS` | Anxious first-timer | 50 | 75 | 0.5 | 0.95 | 0.4 |
| `ANGRY_PREMIUM` | Angry premium client | 35 | 45 | 1.0 | 0.6 | 1.0 |
| `LOYAL_AT_RISK` | Loyal but at risk | 60 | 60 | 0.8 | 0.8 | 0.6 |
| `NEW_SUBSCRIBER` | New subscriber | 65 | 85 | 0.3 | 0.7 | 0.3 |

* **Difficulty** changes patience and how hard negative moves hit: `EASY` (penalty x 0.7, patience + 15), `MEDIUM` (x 1.0, 0), `HARD` (x 1.4, - 15).
* **Intent** is the opening sentence: `BILLING` ("I was charged twice on my September bill."), `ROAMING` ("My roaming bundle did not work abroad."), `CANCELLATION` ("I want to cancel, and this fee makes no sense.").
* **Mixing**: a second persona can be blended in (the sensitivities are averaged, mood and patience averaged and truncated).
* **Memory** ("repeat contact"): the opening adds "This is the third time I call about it.", empathy helps more, and being asked to repeat hurts 1.3 times more.

### 3. How each move changes mood and patience
`neg` is the difficulty penalty. Results are rounded (JavaScript's rounding, so the numbers match the TypeScript version) and kept within 0 to 100.

| Move | Mood change | Patience change | Other |
|---|---|---|---|
| `EMPATHY` | + (10 + 14 x empathy) with memory, else + (4 + 8 x empathy) | + 4 | |
| `ASK_REPEAT` | - (8 + 10 x repeat) x neg (x 1.3 with memory) | - (10 + 12 x repeat) x neg | effort + 1 |
| `TRANSFER` | - 8 x neg | - (8 + 10 x speed) x neg | effort + 1 |
| `CHECK_POLICY` | + 2 | - (4 + 6 x speed) x neg | policy checked |
| `PROMISE` | + 14 | + 5 | **risky** if the policy was not checked first |
| `RUDE` | - 18 x neg | - (18 + 8 x speed) x neg | **rude**: the call cannot end as resolved, churn + 10, a conduct note; three in a row make an impatient customer hang up |
| `OTHER` | + 1 | - 3 | |
| `FOLLOW_UP` | + (8 + 6 x empathy) | + 6 | **closes the call** |

### 4. When a call ends and what the verdict says
A call ends when patience reaches 0 (**the client hangs up**), when the advisor makes a `FOLLOW_UP` (**closed**), or after 6 moves. The outcome contains:
* `expectationMet`: closed, not risky, not rude, not hung up, and mood at least 55.
* `churnRisk` = 100 - 0.55 x mood - 0.35 x patience + 7 x effort + 12 (if risky) + 10 (if rude) + 25 (if hung up), clamped to 0 to 100.
* `verdict`: "The client hung up." / "Resolved: the client leaves satisfied." / "Closed, but trust is shaky." / "Call left open."
* `notes`: customer effort ("had to repeat or be transferred n time(s)"), compliance risk ("a refund was promised before the policy was checked"), conduct ("the advisor raised their voice or was rude"), memory ignored, no written follow-up.

### 5. The customer's words
The reply depends on the move, the mood band (below 30 upset, below 60 unsure, else content) and the persona. Each move has 3 or 4 sentences per band; a persona "flavour" is added two times out of three ("I pay a premium price for better than this."); a hung-up customer says one of three goodbyes. The choice among sentences is a hash (FNV-1a) of persona, intent, move, turn and what the advisor typed, so a call replays identically.

**She answers what was actually said.** When the advisor's words match no move (`OTHER`) she still reacts to them: if they contain an **amount** ("$2,000", "45 TND") she questions it ("Why are you talking about $2,000? That is not what I called about."); a **greeting** gets a greeting and the subject of the call ("Hello. So, about my bill?"); a **question** gets a puzzled answer that brings the subject back. Each has two lines per mood band and names the call's subject (my bill, my roaming bundle, my cancellation). A `RUDE` move has its own lines per band ("Don't shout at me!", "Excuse me? There's no need to raise your voice.", "Oh... did I say something wrong? You sound upset.").

**She hears the voice.** A voice note is transcribed *and* sent to the emotion model ([08-emotion-model.md](08-emotion-model.md)); the web app passes its reading (`tone`: an emotion and a 0 to 100 mood) with the words. If the voice was clearly angry the move is `RUDE` whatever the words say, so a polite sentence screamed gets a reaction. Only anger or disgust with a mood of 30 or lower counts; a weak reading, or another emotion, is ignored. A language model could replace `read_advisor` and `customer_line` (same signatures); nothing else changes.

## Data
No data files. Everything above is in `customer.py`; the hand-written sentences are the only "content".

## API (agents service)
| Endpoint | Body | Answer |
|---|---|---|
| `POST /customer/sessions` | `persona`, optional `mix`, `difficulty` (default MEDIUM), `intent` (default BILLING), `memory` (default false) | `{id, persona, opening, mood, patience}`; the id is 16 hexadecimal characters |
| `POST /customer/sessions/{id}/say` | `text` (1 to 300 characters), optional `tone` `{emotion: anger/disgust/fear/happy/neutral/sad, mood: 0 to 100}` | `{ended, outcome, mood, patience, client, move, moveLabel}`; after the end it answers the outcome again; unknown id: 404; a tone that is not valid: 422 |

Sessions live in memory (200 at most; the oldest is dropped; a restart ends open calls). `transcript(id)` returns the call as turns for the quality analyst.

## In the web app
* **Client workspace** (`/client`, `yasmine`): the TypeScript engine plays in the page. Pick a persona, a second persona to mix, a difficulty, an intent and "repeat contact"; then click a move or type a reply. A mood curve, the outcome and a "customer effort" note appear. The URL holds the whole call, so a link replays it.
* **Advisor console, "Live call with a simulated customer"** (`/advisor`, `karim`): the Python simulator answers in real time through the gateway; the customer's reply is spoken in a voice per persona, faster when upset ([07-voice.md](07-voice.md)); the advisor agent suggests the next answer after each customer message; the advisor can type or record a voice note; **Send to quality review** hands the call to the quality analyst ([04-quality-analyst.md](04-quality-analyst.md)).

## Explainability
Every customer reply shows *"She read this as: ..."* (the move the rules recognised), and mood and patience are drawn after every turn. The outcome lists the reasons (effort, risk, memory). The mood changes are the formulas above, so nothing is hidden.

## Tests
* `services/agents/tests/test_agents.py`: two golden tests replay recorded cases (`tests/golden_customer.json`, produced by the TypeScript engine): reading the advisor gives the same moves, and every call replays with the same opening, moves, lines, mood and patience; plus a live call over HTTP and refusal of bad input. Four more: a raised voice, rude words and shouting are read as `RUDE` (and acronyms are not shouting); a raised voice costs patience, spoils the ending and is noted; she answers an amount, a greeting or a question; the tone of a voice note reaches her over HTTP (and a tone that is not valid is refused). `tests/regenerate_golden.mjs` rebuilds the golden calls from the compiled TypeScript engine.
* Web: client page and simulator routes; live-call routes (`live-call.spec.ts`); browser tests for the live call.

## Honest limits
Rule-based language: unusual phrasing is read as `OTHER` (and answered only if it holds an amount, a greeting or a question), so she follows the *kind* of thing said, not its meaning; the tone is only read for voice notes (not for typed text, where capitals, exclamation marks and insults stand in for it), and the emotion model was trained on acted speech, so a loud happy voice can be misread as anger (the threshold of 30 keeps that rare, it does not remove it); replies repeat after a few calls; five personas and three intents only; one call topic per intent. Mood bands are coarse. A real LLM would give variety but needs a safety layer so it cannot invent policy; the move-based dynamics would still decide mood and churn.

## Files
`services/agents/customer.py`, `app/src/pages/client-simulator.ts`, `app/src/pages/customer-llm.ts`, `app/views/client.njk`, `services/agents/tests/golden_customer.json`.
