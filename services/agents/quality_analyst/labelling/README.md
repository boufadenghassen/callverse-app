# Human-agreement study (labelling sheet)

Why: the analyst's 99 % F1 is measured on calls and labels that we wrote ourselves. This study asks two other people to judge the same calls, blind, and measures (1) how much people agree with each other, (2) how the analyst compares with them.

## Run it
1. Build the sheet (same sheet every time, `SEED = 7`):
   `../../../venv/Scripts/python.exe -m quality_analyst.labelling.make_sheet` (from `services/agents`).
   It writes `data/labelling/labelling-sheet.html` (give this to the labellers) and `data/labelling/answer-key.json` (keep this one to yourself). Both are git-ignored.
2. Two people open the HTML file in a browser, work alone, tick the problems per call and press *Download my labels*; they send back `labels-<name>.json`.
3. Score:
   `../../../venv/Scripts/python.exe -m quality_analyst.labelling.agreement data/labelling/answer-key.json labels-a.json labels-b.json`

## What the sheet contains
50 calls: 30 short hand-written cases (held-out test split, every rule at least once) and 20 simulated history calls spread from worst to best score, mixed and renamed L01 to L50. No analyst result and no expected label is inside the HTML (a test checks it). 18 yes/no questions per call, one per rule, each explained in plain words, plus the company facts.

## Reading the report
Kappa is agreement beyond chance (0 = chance, 1 = perfect; above 0.6 is usually called good). If the two people agree with each other much less than the analyst agrees with them, the labels are the weak point, not the analyst: fix the rule definitions in `make_sheet.DEFINITIONS` and redo. Discuss the calls in part 4 of the report before trusting any number.

## Limits
The calls are still simulated or written by us: the study checks the labels and the judgement, not real customers. Real recordings can replace `history_calls()` in `make_sheet.py`; nothing else changes.
