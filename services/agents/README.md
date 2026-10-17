# orqestra agents service (Python, FastAPI)

The real agents behind the web app's `AgentGateway`. Built so far:

| Agent | Endpoints | How it works |
|---|---|---|
| **Customer simulator** | `POST /customer/sessions`, `POST /customer/sessions/{id}/say` | A persona with mood and patience. It reads what the advisor typed (`read_advisor`), updates mood, patience and churn by fixed rules, and answers (`customer_line`). A port of the web app's training simulator: `tests/test_agents.py` replays recorded calls from the TypeScript version and checks that every turn is identical. No LLM yet; swap `read_advisor` and `customer_line` in `customer.py` and keep their signatures. |
| **Customer advisor** | `POST /advisor/suggest` | TF-IDF retrieval over the demo knowledge base `knowledge/base.json`. Returns the answer, its sources, the match score, detected intents, and a policy warning (refund above 50 TND needs a supervisor). Says so when nothing matches. The confidence is the cosine similarity of the best passage, not a probability. |

The other agents (workforce, quality, complaints, training, sales) still use demo data in the web app. `HttpAgentGateway` starts
from the demo data and replaces only what exists here, so `AGENTS_MODE=http` already works.

## Run (from this folder)

```
../../../venv/Scripts/python.exe -m uvicorn main:app --port 8000
```

Then start the web app with `AGENTS_MODE=http` (and `CALLVERSE_AGENTS_URL` if the port differs). Open the **Advisor console** as `karim`,
section "Live call with a simulated customer".

## Test

```
../../../venv/Scripts/python.exe -m pytest -q
```

`tests/golden_customer.json` was produced from the compiled TypeScript simulator; regenerate it if the rules in
`app/src/pages/client-simulator.ts` or `customer-llm.ts` change (and change `customer.py` the same way).

## Limits

Live calls are kept in memory (200 at most): restarting the service ends open calls. The knowledge base is invented demo content
for a fictional operator, to be replaced by the real FAQ.
