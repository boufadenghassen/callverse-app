# Presentation facts: every claim, where it comes from, how to check it

The rule for the presentation: **we say nothing that is not on this page.** Each line gives the claim as it is on a slide, the evidence, and how anyone can re-check it.
State of the project: branch `integration/presentation`, checked on 2026-10-22 on one machine (Windows, RTX 4060). Slide numbers are those of the deck (26 slides).

## 1. Re-check everything in five commands

| What | Command (from the repository root) | Expected |
|---|---|---|
| Python agents | `..\venv\Scripts\python.exe -m pytest -q` in `services\agents` | 205 passed (about 100 s) |
| Models | `..\venv\Scripts\python.exe -m pytest -q models\tests` | 4 passed |
| Web app | `npm test` in `app` | 117 pass |
| Browser, real agents | start everything (`start-all.bat`), then `npm test` in `app\e2e` | 46 tests: 45 pass, 1 skipped by design (the demo-mode complaints test skips itself when the real agents run; the next test covers the same page) |
| Accessibility | `node audit.mjs` in `app\e2e` | `NO PROBLEMS FOUND` (axe, every page, light and dark) |

**372 automated tests** = 205 + 4 + 117 + 46. None fails. The browser tests add reviews and cases to the local stores, so **run `start-all.bat -Clean` after testing and before presenting**.

## 2. Claims by slide

| Slide | Claim on the slide | Evidence | How to check |
|---|---|---|---|
| 1, 6, 8, 9 | Seven agents, one per persona, all running | `docs/agents/README.md` (status table), `GET http://localhost:8000/health` lists the agents | open `/health`; each agent has its chapter `docs/agents/01` to `06` |
| 3 | Seven personas (Yasmine, Karim, Sana, Nour, Rim, Amine, Leila) | `app/src/auth/auth.service.ts` (the accounts), `/personas` | sign in as each |
| 5 | 28 ideas: 12 production, 12 prototype, 4 perspective | `app/src/pages/deck-content.ts`; test `deck-and-simulator.spec.ts` ("28") | `/ideas`, filter by decision |
| 9 | 21 ideas demonstrated, 6 partial, 1 on the roadmap | the same file, column "coverage" | count the rows with LIVE, PARTIAL, ROADMAP (21, 6, 1) |
| 7 | Node.js, NestJS, TypeScript, server-rendered; gateway demo or real; no Streamlit | `app/` (NestJS), `app/src/agents/` (gateway), `AGENTS_MODE` in `app/README.md` | `AGENTS_MODE=http` calls Python, default `mock` does not |
| 7 | 372 tests: 117 web, 46 browser, 205 Python, 4 models | section 1 above | the five commands |
| 7 | 0 accessibility violations on the tested pages | `app/e2e/audit.mjs` | `node audit.mjs` |
| 7 | Agents, voice and emotion model run locally | Whisper `base.en` and Kokoro (`docs/agents/07-voice.md`), WavLM service on port 8001 (`docs/agents/08-emotion-model.md`) | `start-all.bat` starts all three on the machine (the models are downloaded once); the optional LLM enrichment of the Training agent is off |
| 8 | What each agent does and what it is built on | chapters `docs/agents/01` to `06` | read the "What it is not" section of each |
| 10 | Policy alert above 50 TND needs a supervisor | `services/agents/knowledge/base.json` (Billing policy §4.2), `docs/agents/02-customer-advisor.md` | the console shows "Refunds above 50 TND need supervisor approval" |
| 11 | The customer answers live and out loud, with mood and patience | `docs/agents/01-customer-simulator.md`; voice: `docs/agents/07-voice.md` | `/advisor`, "Start call" |
| 11 | The tone of the advisor's voice note changes the customer's reaction (a rude move when the emotion model hears anger or disgust and the mood is 30 or less) | `docs/agents/01-customer-simulator.md`, tests in `services/agents/tests/test_agents.py`, `app/test/customer.spec.ts` and `app/test/live-call.spec.ts` | record an angry voice note in the console |
| 12 | Training agent: 15 problems, three languages (English, French, Tunisian Arabic), 17 complications; a seeded generator | `services/agents/scenario_gen/README.md`, `docs/agents/06-training-and-complaints.md` | `/training` |
| 12 | A scenario can be played in the console; the advisor agent can play it | `app/src/pages/scenario-sim.ts`, test `auto-call.spec.ts`, browser test "a training scenario can be played" | `/training`, open a scenario, "Play it in the console" |
| 13 | The advisor agent answers by itself in four steps, from the sourced answer; it is not a language model | `services/agents/advisor.py` (`auto_reply`), `docs/agents/02-customer-advisor.md` | "Let the advisor agent talk" |
| 13 | Careful advisor: 90 / 100, the customer leaves satisfied. Rushed advisor: 38 / 100, the customer hangs up, the call is listed as a possible complaint | browser tests "the advisor agent talks by itself" and "a rushed advisor ends the call badly, and the call shows up for the complaint agent"; both scores seen on the clean state on 2026-10-22 | run both buttons; **the score can differ by a few points on another run: read what the screen shows** |
| 14 | A two-channel recording: Whisper transcript by speaker, emotion of the customer's voice, 18 rules, five criteria, here **33 / 100**, coaching hint **+8** | `docs/agents/04-quality-analyst.md` (the 18 rules); the sample call of the Quality page | `/quality`, "Download a sample call", upload it as "Karim B.": re-checked on 2026-10-22, result 33 / 100 and "+8" |
| 15, 16, 17 | Every effect is a what-if: the call is scored again with only that one thing changed; a dispute recomputes everything | `docs/agents/04-quality-analyst.md` ("What moved this score"), quality tests | open "What moved this score" on any review, mark a finding "Not an error" |
| 16 | The slide's example (a call scored 80 / 100: −10 for 120 dinars without approval at 00:19, +12 for checking the policy) | a real screenshot of a call reviewed while building (`presentation-shots/quality-drivers.png`) | **not a button you can press**: on stage show the review of the call you have just made; its numbers differ, its structure is the same |
| 18 | Emotion model: 74 % on actors it has never seen, 71.5 % mean under 10 phone-line degradations | `docs/agents/08-emotion-model.md` (73.8 %, 71.5 %), `models/reports/` | read the table; acted speech (CREMA-D, RAVDESS), not real customers |
| 18 | Occlusion map: silence a quarter of a second at a time, score again | `models/src/explain.py`, `models/tests/test_explain.py` | Call review page |
| 19 | The spike arrives at 2 pm (81 calls per hour, estimated service level 68 %); extra advisors simulated; Erlang C; routing moves checked by simulation (68 % becomes 72 % with 3 moves; the independent simulation says 70 % becomes 74 %) | `docs/agents/03-workforce-manager.md`; the numbers are on the Workforce page on the clean state | `/workforce`, scrub to 14h, "Run simulation" |
| 19 | The call history is synthetic | `docs/agents/03-workforce-manager.md` | said on the slide |
| 20 | An offer's relevance is a sum of points: for Yasmine Toumi 36 = +25 +15 +10 −10 −4; without the open ticket 46 | `docs/agents/05-sales-agent.md`, `/sales` | "Why this offer" |
| 20 | Replay of selling rules on the simulated history: offering at every chance 7,235 TND, 28 % yes, 215 refused; relevance 70 or more at a good moment 52 % yes, 42 refused, 3,474 TND | `services/agents/sales_agent/store.py` (`simulate`, history seeded with 240 simulated offers, seed 11); screenshot of the clean state | `/sales`, "What a selling rule would earn"; **only on the clean state: clicking "Customer accepted" or "Declined" adds to the history and moves the numbers** |
| 20 | Churn risk and the chance of a yes are hand-weighted, counted from the history, not learned | `docs/agents/05-sales-agent.md` | read the "Why this churn risk" panel |
| 21 | CMP-221: severity 51 = +15 +12 +8 +16; escalation risk 86 from seven factors | `docs/agents/06-training-and-complaints.md`, `services/agents/complaints_agent/engine.py` | `/complaints/CMP-221`; **right after a clean start**: later the time-pressure factor grows and the risk changes |
| 21 | Deadlines 12 h critical, 24 h high, 48 h medium, 72 h low; follow-up call after 72 h; an upset customer reopens | `services/agents/complaints_agent/engine.py`, test `test_complaints.py` | open any case |
| 21 | A call that ended badly is listed under "calls that may be complaints" | browser test "a rushed advisor ends the call badly, and the call shows up for the complaint agent" | run the rushed call, open `/complaints` |
| 22 | Analyst F1 99 % on 91 held-out calls, labels written by us | `docs/agents/04-quality-analyst.md` ("Measured accuracy"), the Accuracy section of the Quality page | read the limits next to the number: our calls, our labels, short calls |
| 22 | First user feedback: none; an agreement study between two labellers on 50 calls is prepared, **no results yet** (the label files of two teammates are missing) | `services/agents/quality_analyst/labelling/` | nothing to check: it is a gap, said as a gap |
| 23 | First measure on 44 hard unseen calls: F1 75 % (keywords), 81 % (with the semantic opinion) | `docs/agents/04-quality-analyst.md` ("The journey") | the Accuracy section of the Quality page |
| 23 | A 17 s first computation fixed by a warm-up | `services/agents/main.py` (`_warm_up`) | start the agents, the first review is fast |
| 24 | One script starts everything | `start-all.ps1`, `start-all.bat` | run it |

## 3. What we do not claim

* **No language model** anywhere by default: the customer, the advisor (also when it talks by itself), the scores and the scenario generator are rules, retrieval, formulas and templates. The optional enrichment of the Training agent through an LLM API is off.
* **No real data**: customers, calls, cases, offers, call history, the knowledge base and the complaint history are invented or simulated. The emotion model was trained on acted speech.
* **No learned prediction** of churn, of a yes, of escalation or of complaints: they are sums of named points with hand-set weights.
* **No reinforcement learning** in the workforce routing: it is a local search whose moves are checked by simulation.
* **No user test** with real advisors, analysts or customers yet.
* **No result** from the human-agreement study yet.
* The Training agent's scenarios are played through a translation to our simulator's settings: his 15 problems go to our three reasons for a call, and language and some complications are shown but not played.
* **Not production**: demo password, sessions in memory, SQLite files, no real sign-in.

## 4. Numbers that move (and what to do about it)

| Number | Why it moves | Before presenting |
|---|---|---|
| Complaint deadlines, time pressure, "past their deadline" | cases age in real time from the moment they are seeded | `start-all.bat -Clean` less than an hour before; right after it: 6 open cases, CMP-221 at 51 and 86 |
| Sales replay, track record in the offer reasons | clicking "Customer accepted" or "Declined" adds to the history | `-Clean`, and do not click those buttons before the replay |
| Quality team average, number of reviews, call ids | every live call, upload and browser test adds a review | `-Clean` (84 simulated calls) |
| The score of an automatic call | the customer simulator has random moments and the advisor routine is fixed | run it once before; say "about 90" and "under 40", read the screen |
| Scenario ids (`sc_...`) | the generator makes a new scenario when asked | none: the ids on the slides are examples |

`-Clean` moves the three local stores to `services\agents\data\backup-<date>`; nothing is deleted.
