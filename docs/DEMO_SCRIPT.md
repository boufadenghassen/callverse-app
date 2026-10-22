# Demo script and rehearsal checklist

For the presentation of orqestra (26 slides, English). Everything runs on one Windows machine. Facts and evidence for every number: [`PRESENTATION_FACTS.md`](PRESENTATION_FACTS.md).
The speaker notes of each slide in the deck repeat the key sentences and the limits to say out loud.

## 1. The day before and one hour before

**The day before** (once): start everything, run the whole script below once, and check the log folder is empty of errors (`%TEMP%\orqestra-logs`).
Run the tests once if you want (`PRESENTATION_FACTS.md`, section 1), but know that they add data: you clean up afterwards.

**One hour before** (every time):

1. Close other heavy programs: the GPU and the memory are shared by Whisper, the voice and the emotion model.
2. Plug in the power, sound on, microphone allowed in the browser if you want to show a voice note (otherwise skip it: the call works in text).
3. Start from the clean demo state:
   ```bat
   start-all.bat -Clean
   ```
   It moves the rehearsal data to a backup folder, rebuilds the web app, starts the three services and waits until they answer (one to two minutes). At the end it prints the accounts. Do **not** start it again during the presentation: it would reset the call you want to show.
4. Open `http://localhost:8080`, sign in as **`admin`** (password `demo-password-123`, or the value of `CALLVERSE_DEMO_PASSWORD`). The admin account opens every workspace, so one window is enough. (If you want the persona story, use one private window per account: karim, nour, sana, leila, amine, rim.)
5. Open these tabs in this order, so that a click on the tab bar is the whole navigation: `/advisor`, `/training`, `/quality`, `/workforce`, `/sales`, `/complaints`. Visit each once so the first load is not slow.
6. In the advisor tab, run **"Let the advisor agent talk"** once to warm everything up, then reload the page (the call is gone, the warm-up stays). Delete nothing else.
7. Open the deck in presenter view, on slide 1. Keep the speaker notes visible.

**Do not click "Customer accepted" or "Declined" on the Sales page before the replay slide**: it changes the numbers (see the facts sheet, section 4).

## 2. The run, slide by slide

Full version: about 21 minutes. Short version (about 17 minutes): skip slides 4, 16, 17 and 19.

| Slides | What | Time | You do |
|---|---|---|---|
| 1 to 6 | Opening, plan, problem, journey, ideation, solution | 4:00 | talk |
| 7, 8 | Architecture, the seven agents | 2:00 | talk; say once: all seven run, all data is invented, no language model |
| 9, 10 | What works today, preview of the console | 1:30 | talk |
| **11** | **Demo 1: a live call** | 1:15 | tab `/advisor` (below) |
| **12** | **Demo 2: a training scenario** | 0:45 | tab `/training` (below) |
| **13** | **Demo 3: the agents run a call by themselves** | 1:30 | tab `/advisor` (below) |
| 14 | The quality analyst on a recorded call | 1:00 | slide, or tab `/quality` (below) |
| 15 to 18 | Explainable AI: the boxes, the evidence, the transcript, the emotion model | 3:15 | slides |
| 19 | Workforce | 1:00 | slide, or tab `/workforce` |
| 20 | Sales | 1:00 | tab `/sales` |
| 21 | Complaints | 1:00 | tab `/complaints` |
| 22 to 24 | Results, difficulties, strengths and limits | 2:30 | talk; **read the limits aloud** |
| 25, 26 | Next steps, questions | 0:45 + Q&A | talk |

### Demo 1, slide 11: a live call (1 min 15 s)
1. `/advisor`. Under "Live call with a simulated customer", keep the default customer and press **Start call**. The customer speaks out loud (untick "Speak her replies" if the room is noisy).
2. Point at the mood and patience bars and at "Advisor agent suggests" with its sources.
3. Press **Use suggested answer**, then **Send**. The customer answers and the mood moves.
4. Say: the customer is made of rules, not a language model. Optional, if the microphone works: **Record voice note**, speak sharply: the customer reacts to the tone.
5. Press **Send to quality review** only if time allows. Otherwise go back to the slides.
*If it fails:* the slide shows a finished call. Say "here is a call we ran earlier" and continue.

### Demo 2, slide 12: a training scenario (45 s)
1. `/training`: the coach plan for the advisor, then the scenarios. Open the first scenario.
2. Read two lines of it: the customer situation, the success criteria. Say: this scenario was generated from the advisor's weak quality criteria; the generator is Selim's.
3. Press **Play it in the console**. The advisor console opens with the settings already chosen and a box saying how the scenario was read; the call starts on arrival and the customer speaks its first sentence. Point at the box, then go straight to demo 3.
*If it fails:* the slide shows the scenario page.

### Demo 3, slide 13: the agents run a call by themselves (1 min 30 s)
1. On the advisor console (the one that demo 2 just opened, with the scenario's settings): press **Let the advisor agent talk**. It starts a new call with the same settings; wait about 10 to 20 seconds while it plays out by itself.
2. When "What the agents did on this call" appears, read it line by line: the simulator's outcome, the advisor's four steps, the sales agent's offer and its timing, the quality analyst's score (about 90) with what lowered it and what went well, and the complaint agent's verdict (no complaint).
3. Press **Show a rushed advisor**. About 15 seconds later the same box reads: the customer hung up, the score is under 40, the complaint agent lists the call.
4. Open `/complaints`: the call is under "Calls that may be complaints". (If the tab is open, press reload.)
5. Say: the advisor agent is a fixed routine built from the sourced answer. It is not a language model and it does not read the customer's mood.
*If it fails:* the slide shows both results. Say "this is what it produced when we ran it".

### Slide 14: the quality analyst (optional live part)
On `/quality`: **Download a sample call**, then upload it (field "Advisor": Karim B.). The first review takes up to a minute (Whisper). Result: **33 / 100**, coaching hint **+8**, five criteria, a transcript by speaker. Do this live only if you have time; otherwise use the slide.

### Slide 19: workforce (optional live part)
`/workforce`: scrub to 14h (81 calls per hour, estimated service level 68 %), enter two extra advisors from 14 to 16 in queue B, **Run simulation**.

### Slide 20: sales (live)
`/sales`: open "Why this offer" on a card (every score is a sum of points). Scroll to **What a selling rule would earn** and press **Simulate** with the defaults: offering at every chance 7,235 TND and 28 % yes; relevance 70 or more at a good moment 52 % yes and 42 refusals. Say: simulated history, hand-weighted scores.

### Slide 21: complaints (live)
`/complaints`: the early warning and the six open cases. Under "Read a complaint" press **Legal threat**, then **Read it**: the root cause, the severity, the risk and the deadline with their points. Open CMP-221: severity 51 and risk 86, each a list of named points.

## 3. If something goes wrong

| Problem | What to do |
|---|---|
| A page says the agents are not running | Open `%TEMP%\orqestra-logs\agents.err.log`; run `start-all.bat` (not `-Clean`) to restart. Meanwhile, use the screenshots on the slides. |
| The call does not speak | Untick "Speak her replies": the call works in text. |
| The first review of a recording is very slow | Whisper and the emotion model load on first use; this is why step 6 of "one hour before" warms them up. Skip it and show the slide. |
| The numbers differ from the slides | Read the number on the screen and say "it varies slightly between runs". The slides come from the clean state; the facts sheet lists what moves. |
| The browser asks to save the password | Decline. |
| A page shows demo data and no agents | The web app is in demo mode (`AGENTS_MODE=mock`): restart with `start-all.bat`. |
| Everything is down | Stay on the slides. They carry real screenshots of every demo, and say so. |

## 4. Questions to prepare (short, honest answers)

| Question | Answer |
|---|---|
| Is there a language model? | No. Rules, retrieval, formulas and templates. An LLM judge next to the rules, compared on the same calls, is the first next step. The Training agent can optionally use one; it is off. |
| Is the data real? | No: customers, calls, cases, offers and history are invented or simulated; the emotion model was trained on acted speech. |
| How accurate is the quality analyst? | 99 % F1 on 91 held-out calls, but they are calls we wrote and labelled ourselves. An agreement study with two independent labellers is prepared; its results are missing. |
| Does the emotion model work on real customers? | Not measured. 74 % on unseen actors, 71.5 % under phone-line degradations. |
| Does routing use reinforcement learning? | No, a local search whose moves are checked by simulation. |
| Did you test with real users? | Not yet. The next step is trials with advisors and analysts. |
| How do the agents work together? | Through one API contract and a gateway: the pages do not change when an agent is replaced. On a call: the scenario sets the customer, the advisor answers, the sales agent proposes an offer and a timing, the quality analyst scores, the complaint agent lists a bad call, and the coach plan turns the weak points into new scenarios. |
| Who built what? | The team built it together; the Training agent is Selim's scenario generator. Authorship of each part is in the git history. |
| What would it take to go to production? | Real sign-in, a real database instead of SQLite files, containers, real call data, user tests. |

## 5. What not to say

* "AI that predicts churn / complaints": the scores are explainable sums of points, not trained predictions.
* "Trained on real calls", "validated by users", "99 % accurate" without "on calls we wrote ourselves".
* "Reinforcement learning", "LLM", "GPT".
* Any number that you did not see on the screen or on this page.

## 6. Rehearsal checklist

- [ ] Rehearsal 1 with the deck and the live demos, timed (target 17 to 20 minutes).
- [ ] Rehearsal 2 with a teammate who asks three questions from section 4.
- [ ] `start-all.bat -Clean` ran without error; the three services answer (`http://localhost:8000/health`, `:8001/health`, `:8080`).
- [ ] Demo 1, 2 and 3 each worked at least twice in a row.
- [ ] Both automatic calls (careful about 90, rushed under 40) gave the results of slide 13; the rushed call appeared under Complaints.
- [ ] Complaints: 6 open cases, CMP-221 at 51 and 86 (clean state, less than an hour old).
- [ ] Sales replay shows 7,235 TND / 28 % and 52 % / 42 refusals (clean state, nothing accepted or declined).
- [ ] Sound and the browser microphone permission tested in the room, or the voice demo skipped on purpose.
- [ ] The limits slide (24) and the "what we do not claim" list in the facts sheet read aloud once.
- [ ] A copy of the deck as PDF or PowerPoint and the screenshots folder (`presentation-shots`) on the machine, in case the network is down.
- [ ] After the presentation: `start-all.bat -Stop`.
