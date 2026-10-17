# orqestra web (NestJS)

The orqestra web app rebuilt on **Node.js + NestJS 12**, all in **TypeScript** (server in `src/`, browser script in `client/`). Pages are server-rendered with Nunjucks, so the
strict CSP (no inline scripts or styles) and the existing `public/css/app.css` and `public/js/app.js` work unchanged.
One workspace per persona, each locked to its role.

## Run it

Needs Node.js 22+.

```bash
npm ci
npm run build
CALLVERSE_DEMO_PASSWORD=choose-a-long-password CALLVERSE_COOKIE_SECURE=false npm start
```

Or double-click `start-demo.bat`. Open http://localhost:8080 and sign in as `admin` (sees everything), `yasmine`,
`karim`, `sana`, `nour`, `amine`, `rim` or `leila`. All use the demo password.

| Variable | Meaning |
|---|---|
| `CALLVERSE_DEMO_PASSWORD` | Required, 12+ characters. Shared by the demo accounts. |
| `CALLVERSE_COOKIE_SECURE` | Set `false` only for plain `http://localhost`. |
| `AGENTS_MODE` | `mock` (default) or `http` to call the Python agents. |
| `CALLVERSE_AGENTS_URL` | Base URL of the Python agents, default `http://localhost:8000`. |
| `PORT` | Default `8080`. |
| `SESSION_SECRET` | Optional. Without it a random secret is made at start, so sessions end on restart. |

## Layout

```
src/main.ts, setup.ts        bootstrap: views, static files, CSP and other headers, sessions
src/auth/                    demo accounts + lockout, AccessGuard (CSRF, sign-in, @Roles), login/logout
src/agents/                  AgentGateway (abstract), MockAgentGateway, HttpAgentGateway
src/pages/                   controllers, Client Simulator, deck content, SVG chart builders
src/errors.filter.ts         friendly error pages (503 when an agent is down)
views/                       Nunjucks page templates (HTML)
client/app.ts                browser script in TypeScript, compiled to public/js/app.js by `npm run build`
public/css/app.css           the styles (CSS stays CSS)
test/                        node:test + supertest (26 tests); e2e/ has the 12 Playwright browser tests
```

Tests: `npm test`. Browser tests (app must be running): `cd e2e && npm install && npm test`.
Docker: `docker build -t callverse-nest .` then
`docker run -p 8080:8080 -e CALLVERSE_DEMO_PASSWORD=... -e CALLVERSE_COOKIE_SECURE=false callverse-nest`.

## Agent API contract (what the Python side must expose)

`HttpAgentGateway` (`AGENTS_MODE=http`) calls these. Responses are JSON with the camelCase field names of the
interfaces in `src/agents/models.ts`. In FastAPI, use Pydantic models with `alias_generator=to_camel`.

| Method | Path | Returns |
|---|---|---|
> **Built in `services/agents`:** `/advisor/suggest`, `/customer/sessions` and `/customer/sessions/{id}/say` (marked ✔ below).
> `HttpAgentGateway` keeps demo data for every other row until its Python agent exists.

| GET | `/advisor/customers/{id}` | CustomerContext |
| POST | `/advisor/suggest` `{customer_id, query}` ✔ | SuggestedAnswer (with optional `intents`, `evidence`) |
| POST | `/customer/sessions` `{persona, mix, difficulty, intent, memory}` ✔ | CallStart |
| POST | `/customer/sessions/{id}/say` `{text}` ✔ | CallReply |
| GET | `/workforce/forecast?queue=B` | ForecastPoint[] |
| POST | `/workforce/simulate` | SimulationResult |
| GET | `/quality/reviews?limit=20` | QualityReview[] |
| GET | `/complaints/open` | ComplaintCase[] |
| GET | `/training/scenarios` | Scenario[] |
| GET | `/sales/opportunities` | Opportunity[] |

## Voice

Agent answers (advisor suggestions, quality coaching hints, workforce recommendations) have a **Listen** button, and the advisor's live call
speaks the customer's replies, faster and higher when she is upset, calmer when she is content (switch: "Speak her replies",
remembered). It uses the neural voice of the Python agents (`POST /voice/speak`, see `services/agents/README.md`) and falls back to the browser's built-in speech when that is not available. Nothing leaves your machine either way.
Mark any text with `data-speak` to give it a Listen button.
