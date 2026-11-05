# Complaint agent (Amine)

Reads a complaint, finds its root cause, says how serious it is and how likely it is to escalate, gives the deadline, raises the early warning and lists what to do first. Every score is a sum of named factors with the reason in words. Classification is hybrid: high-signal rules first, the optional supervised character TF-IDF + Logistic Regression model trained on the reviewed Comcast gold set, then TF-IDF prototype similarity, with an explicit `other` result when confidence is low. The model keeps the dataset label for audit and maps it explicitly to the operational categories used by this agent.

| File | What it does |
|---|---|
| `classifier.py` | explainable hybrid classification: rules, optional supervised model, TF-IDF fallback and confidence |
| `ml_model.py` | supervised character TF-IDF + Logistic Regression training, held-out metrics and model loading |
| `train_model.py` | command-line training entry point |
| `dataset.py` | optional, read-only CSV summary for external complaint data |
| `rules.py` | shared policy loading |
| `engine.py` | root cause (clusters from `../knowledge/complaints.json`), severity, deadline, escalation risk, early warning, first actions, `triage` of an unsaved complaint |
| `store.py` | SQLite cases and their log (`../data/complaints.db`, git-ignored, `COMPLAINTS_DB` to move it), the life of a case (take, escalate, resolve, close after the follow-up, reopen), the simulated history, the insights |
| `api.py` | the `/complaints` router mounted by `main.py` |
| `tests/test_complaints.py` | the agent's tests |

Endpoints: `GET /complaints/open`, `GET /complaints/{id}`, `POST /complaints/triage`, `POST /complaints`, `POST /complaints/{id}/{take|escalate|severity|alert|resolve|close|reopen}`, `GET /complaints/follow-ups`, `GET /complaints/insights`, `GET /complaints/from-calls`, `POST /complaints/from-call`. Web side: `app/src/pages/complaints.controller.ts`, `app/views/complaints.njk` and `complaint.njk`.

The open cases age in real time. Delete `data/complaints.db` (with the service stopped) to restart the demo clock.

Tests, from `services/agents`: `pytest -q complaints_agent/tests`

`GET /complaints/model` reports the classifier method and limitations. The trained model's held-out metrics are stored beside the model in `data/complaints_model.metrics.json`; the source ZIP report is a separate 5-fold evaluation and should not be confused with this local hold-out score.

To train from an annotated file:

```text
python -m complaints_agent.train_model complaints_labeled.csv complaints_model.joblib
COMPLAINTS_MODEL_PATH=...\complaints_model.joblib
```

`data/gold_final.csv` contains 300 human-reviewed labels from the imported dataset. `data/report_02.json` records the source project's 5-fold result (best model: character TF-IDF + Logistic Regression, macro-F1 0.6624). `data/split_report.json` records the raw-data cleaning and split provenance. `data/complaints_labeled.example.csv` remains only a schema example.

Dataset labels are mapped as follows: `BILLING` to `billing_amount`, `CONTRACT_PLAN` to `contract_terms`, `CUSTOMER_SERVICE` to `repeat_contact`, `FIELD_SERVICE` to `device`, `NETWORK_TECH` to `network`, and `FRAUD_PRIVACY_LEGAL`, `POLICY_COMPETITION`, and `OTHER_UNCLEAR` to `other`. The original dataset label is returned as `datasetLabel`.
