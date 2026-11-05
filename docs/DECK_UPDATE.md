# Deck update: what to change after the advisor and Training work (2026-11-05)

The 26-slide deck could not be opened from the account used on 2026-11-05, and its builder scripts were in a temporary folder that no longer exists. So the deck itself is **not updated yet**. This sheet lists every change. Slide numbers come from `PRESENTATION_FACTS.md`; the current wording of the slides was not visible, so match the claims, not the exact words.

New screenshots (real, light theme) are in `Desktop\PI\presentation-shots`: `advisor-agent-reads-the-call.png`, `advisor-agent-summary.png`, `training-practice-results.png`.

## Slides

| Slide | Replace | With |
|---|---|---|
| 7 | 372 tests: 117 web, 46 browser, 205 Python, 4 models | 396 tests: 122 web, 46 browser, 224 Python, 4 models |
| 7 | Any "no language model" line | One local language model, which writes words and decides nothing |
| 8 | Advisor agent: fixed routine | Advisor agent: rules choose the step, a local model writes it, quality rules check it |
| 8 | Training agent, if it says three languages can be played | The catalogue has three languages; the live simulator plays English |
| 12 | Scenario played through the three simulator reasons | The customer opens with the scenario's own problem. Add: practice results return to the coach |
| 13 | Advisor agent: four fixed steps, does not read the mood | Reads the conversation and the mood, plan, write, check (see below) |
| 13 | Careful advisor 90 / 100 | Careful advisor 99 or 100 / 100. Rushed stays 38 / 100 |
| 13 | The screenshot of the summary box | `advisor-agent-summary.png` |
| Limits (24) | Any "no language model" line | The model decides nothing; a high automatic score proves little (see `PRESENTATION_FACTS.md`, section 3) |
| Next steps | "An advisor agent that reacts to the mood" or "an LLM-backed advisor" | Done. Next: a customer simulator that speaks through the model, an LLM judge next to the rules, a wider knowledge base |

## Slide 13: suggested text

**Title:** The advisor agent reads the call

1. **Plan (rules):** the next step comes from the conversation and the customer's mood.
2. **Write (local model):** qwen2.5:7b words the step from the sourced passage. Nothing leaves the computer.
3. **Check (quality rules):** every draft is read before it is said. A refused draft falls back to fixed wording.

**Result:** 30 real calls, all resolved, average 99.8 out of 100, lowest 99.

## Speaker notes

**Slide 13.** "The advisor agent no longer follows a script. Rules read the conversation and choose the next step: if the customer's mood falls, it calms them first. A small language model on this computer then writes the words from the sourced passage. Before anything is said, the quality analyst's own rules check the draft. If it fails, the agent tries once more, then uses fixed wording. Under each reply you can see why that step was chosen and who wrote it. On 30 calls all were resolved, with an average of 99.8. Be careful with that number: our rules checked the replies and our rules scored them, against a rule-based customer. It shows the process is followed, not that real customers would be satisfied."

**Slide 12.** "A scenario now stays itself on the phone: a lost SIM is a lost SIM. When an advisor practises, the call is scored and compared with their usual level, and the coach gets the next step, such as a harder version or a replay. Practice calls do not count in the advisor's quality averages."

## Demo video

The recorded video (`Desktop\PI\demo-video\orqestra-demo-my-voice.mp4`) shows the old automatic call, and its script says "there is no language model". That sentence is no longer true: record that part again, or cut it.
