# Complaint agent (Amine)

Reads a complaint, finds its root cause, says how serious it is and how likely it is to escalate, gives the deadline, raises the early warning and lists what to do first. Every score is a sum of named factors with the reason in words. No language model, nothing learned; **the cases, customers, deadlines and policies are invented and the history is simulated**. Full documentation: `docs/agents/06-training-and-complaints.md`.

| File | What it does |
|---|---|
| `engine.py` | root cause (clusters from `../knowledge/complaints.json`), severity, deadline, escalation risk, early warning, first actions, `triage` of an unsaved complaint |
| `store.py` | SQLite cases and their log (`../data/complaints.db`, git-ignored, `COMPLAINTS_DB` to move it), the life of a case (take, escalate, resolve, close after the follow-up, reopen), the simulated history, the insights |
| `api.py` | the `/complaints` router mounted by `main.py` |
| `tests/test_complaints.py` | the agent's tests |

Endpoints: `GET /complaints/open`, `GET /complaints/{id}`, `POST /complaints/triage`, `POST /complaints`, `POST /complaints/{id}/{take|escalate|severity|alert|resolve|close|reopen}`, `GET /complaints/follow-ups`, `GET /complaints/insights`, `GET /complaints/from-calls`, `POST /complaints/from-call`. Web side: `app/src/pages/complaints.controller.ts`, `app/views/complaints.njk` and `complaint.njk`.

The open cases age in real time. Delete `data/complaints.db` (with the service stopped) to restart the demo clock.

Tests, from `services/agents`: `pytest -q complaints_agent/tests`
