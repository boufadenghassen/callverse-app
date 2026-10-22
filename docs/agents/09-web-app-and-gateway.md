# 9. Web app and agent gateway (platform)

The web app is what every persona sees. It contains **no machine learning**: it checks who you are, validates what you type, asks the **AgentGateway** for data and draws the page. This document describes the platform around the agents: the pages and who may open them, the gateway that connects them to the Python services, the security measures, how to run it and how it is tested.

## What it is made of
* **NestJS 12** (Node 24) on Express, **server-rendered pages** with **Nunjucks** (autoescaped), one small browser script (`app/client/app.ts`, compiled to `public/js`), plain CSS with a light and a dark theme. Fonts are self-hosted (Plus Jakarta Sans); nothing is loaded from another site.
* Source layout: `app/src/` (`main.ts`, `setup.ts` for views, headers and sessions, `app.module.ts`, `errors.filter.ts`), `auth/` (sign-in and the access guard), `agents/` (gateway, demo data, HTTP gateway, shared types), `pages/` (one controller per workspace), `app/views/` (templates), `app/client/` (browser script), `app/public/` (CSS, fonts, favicon), `app/test/` (unit and HTTP tests), `app/e2e/` (browser tests).

## Accounts and roles
There is **one demo account per persona**, all sharing the password in `CALLVERSE_DEMO_PASSWORD` (never in the code; the app refuses to start with fewer than 12 characters). The password is stored only as a bcrypt hash in memory.

| Login | Role | Opens |
|---|---|---|
| `yasmine` | CLIENT | `/client` (client simulator) |
| `karim` | ADVISOR | `/advisor` (advisor console, live call, "score this call") |
| `sana` | WORKFORCE | `/workforce` (forecast, what-if, routing, breaks) |
| `nour` | QUALITY | `/quality` (quality analyst), `/call-review` (emotion of a recording) |
| `leila` | SALES | `/sales` (offers, conversation reader, conversion) |
| `rim` | TRAINER | `/training` |
| `amine` | COMPLAINT | `/complaints` |
| `admin` | ADMIN | every page |

Open to **every signed-in user**: the home page `/` (cards for the workspaces you may enter, with a live number for each when its agent answers), `/personas`, `/ideas`, `/present` (the full-screen walkthrough with live-demo buttons), `/pipeline`, `/insights` (customer statistics by age, sex and region on 720 synthetic customers; groups under 10 are never shown; includes a fairness note), and the voice endpoints. A page that belongs to another role answers **403 "This workspace is for another role"**.

## The pages and their routes
| Route | Method | Role | What it does |
|---|---|---|---|
| `/login`, `/logout` | GET, POST | public / any | sign in (new session id on sign-in), sign out |
| `/` | GET | any | home, with a live figure per agent (a failing agent only hides its figure) |
| `/advisor?customer=&q=` | GET | ADVISOR | customer 360 and the suggested answer; customer id must look like `YT-1042`, search 3 to 200 characters |
| `/advisor/live/start`, `/advisor/live/say`, `/advisor/live/offers` | POST (JSON) | ADVISOR | start a call with the customer simulator (persona, optional mix, difficulty, intent, memory) and send a reply (1 to 300 characters; call id is 16 hex characters); each answer comes with the advisor agent's next suggestion |
| `/advisor/live/review` | POST | ADVISOR | score the finished live call |
| `/workforce`, `/workforce/simulate` | GET, POST | WORKFORCE | forecast chart, routing plan, breaks; what-if form validated (queue A to E, -5 to +10 advisors, `HH:mm` times, end after start) |
| `/quality`, `/quality/audio`, `/quality/sample-call.wav`, `/quality/feedback` | GET, POST | QUALITY | reviews, analytics, upload of a two-channel recording (up to 11 MB), a sample call, reviewer verdicts |
| `/call-review`, `/call-review/analyze` | GET, POST | QUALITY | emotion of an uploaded recording through the emotion service (up to 15 MB) |
| `/sales`, `/sales/detect`, `/sales/simulate` | GET, POST | SALES | see [05-sales-agent.md](05-sales-agent.md) |
| `/sales/outcome` | POST | SALES, ADVISOR | what the customer did with an offer (the advisor reports it from the live call) |
| `/complaints`, `/complaints/{id}`, and POST `/complaints/triage`, `/complaints/new`, `/complaints/from-call`, `/complaints/{id}/{action}` | GET, POST | COMPLAINT | the complaint agent: lanes with reasons, reading a complaint, the case file and every move on a case ([06-training-and-complaints.md](06-training-and-complaints.md)) |
| `/training`, `/training/scenarios/{id}`, and POST `/training/generate`, `/training/scenarios/{id}/mutate`, `/training/scenarios/{id}/delete` | GET, POST | TRAINER | the Training agent's coach plan, scenario detail, builder, what-if and delete ([06-training-and-complaints.md](06-training-and-complaints.md)) |
| `/client`, `/client/say` | GET, POST | CLIENT | the client simulator (see below) |
| `/voice/speak`, `/voice/transcribe` | POST | any signed in | text to speech, voice note to text plus the tone of the voice from the emotion model ([07-voice.md](07-voice.md)) |
| `/personas`, `/ideas`, `/present`, `/pipeline`, `/insights` | GET | any signed in | the presentation pages |
| `/actuator/health` | GET | none | `{"status":"UP"}`, served before sessions exist |

### The client simulator page (`/client`)
A **stateless TypeScript twin** of the Python customer simulator, so the page works without the agents. The whole call is in the URL (persona, optional mix, difficulty, intent, memory, the moves chosen so far, the sentences typed); the server **replays** it, so the same address always shows the same call and can be shared. The advisor's choices are six buttons (acknowledge, ask to repeat, transfer, check the policy, promise a refund, confirm in writing) or a **typed reply**, read by regular expressions into one of those moves (`customer-llm.ts`, first match wins, `OTHER` when none matches). The page draws the mood curve as SVG and ends the call on a resolution, a hang-up or a churn. Limits: at most 6 moves, a typed sentence is cut at 200 characters, the URL fields are all validated (anything unexpected is a 400). The Python version and its parity tests are in [01-customer-simulator.md](01-customer-simulator.md).

## The AgentGateway: the one door to the agents
The pages never talk to an agent directly. They call the abstract class `AgentGateway` (`app/src/agents/agent.gateway.ts`), which offers one method per thing a page needs:

`customerContext`, `suggestAnswer` (advisor) · `startCall`, `say` (customer simulator, `say` also takes the tone of a voice note) · `speak`, `transcribe` (voice) · `routing`, `schedule`, `forecast`, `simulate` (workforce) · `recentReviews`, `qualityEvaluation`, `qualityFeedback`, `qualityReview`, `qualityAnalytics`, `reviewCall`, `reviewAudio`, `sampleCall` (quality) · `opportunities`, `salesDetect`, `salesOutcome`, `salesAnalytics`, `salesSimulate` (sales) · `openComplaints`, `complaint`, `complaintTriage`, `complaintCreate`, `complaintAct`, `complaintInsights`, `complaintFollowUps`, `complaintCandidates`, `complaintFromCall` (complaints) · `scenarios`, `scenario`, `scenarioLineage`, `generateScenario`, `replayScenario`, `mutateScenario`, `deleteScenario`, `trainingPlan` (training).

The shared types of everything that crosses this door are in `app/src/agents/models.ts`; together with the table in `app/README.md` they are **the contract between the web app and the agents** (a change to either is announced to the team first).

### Two implementations, chosen by one variable
* **`MockAgentGateway`** (default): fixed, invented, deterministic demo data: one customer file (Yasmine Toumi, whatever id is asked), one suggested answer, the 3 demo complaint cards (the complaint agent's pages need the real agents), the 3 scenarios, 2 demo offers, demo reviews, forecast, routing and breaks. The live call still works in demo mode because the mock plays the call with the same TypeScript client simulator as `/client` (at most a few calls kept in memory). Nothing else is needed to run the app, which is how it is shown and how the unit tests run. Features that need a real agent (recording review, reviewer verdicts, sales detection) answer `NeedsRealAgentsError`, shown as a clear message.
* **`HttpAgentGateway`** (`AGENTS_MODE=http`): **extends the mock** and overrides only the agents that exist in Python: advisor, customer simulator, voice, workforce, quality analyst, sales, complaints and the training agent (Scenario Gen). Everything the mock serves is therefore only used when no agents are running. Replacing a demo agent by a real one touches the gateway and the Python service, never the page.

### How the HTTP gateway behaves
* Base address `CALLVERSE_AGENTS_URL` (default `http://localhost:8000`). Every value put in a path goes through `encodeURIComponent`, so user input cannot change the path or add query parameters.
* Timeouts: **5 s** for ordinary calls, **60 s** for speech and transcription (the first call loads a model), **180 s** for recording reviews and anything that may wait for a model.
* A **30-second cache** for data that rarely changes (customer file, forecast, routing, breaks, quality evaluation). Reviews, analytics and sales are **not** cached, so a new verdict or outcome shows at once.
* Errors become typed errors the pages understand: `AgentDownError` (unreachable or 5xx; shown as a friendly 503 page or a JSON message), `UnknownCallError` (a call id the simulator no longer knows, for example after a restart), `CustomerNotFoundError` (404 page), `VoiceUnavailableError` (the browser's own voice takes over), `BadAudioError` (unreadable, silent or too short recording; the message is safe to show), `RejectedError` (a request the agent refused), `NeedsRealAgentsError` (demo mode).
* The home page asks each agent for one figure in parallel and leaves out any that fail, so a sick agent never takes the home page down.

## Security
| Measure | Where | Detail |
|---|---|---|
| Sign-in | `auth.service.ts` | demo password hashed with bcrypt (cost 10); the password is always compared, so response time does not reveal which names exist; after **5 failures** a name is locked for **15 minutes**; names are looked up with `Object.hasOwn` |
| Session | `setup.ts` | cookie `CVSESSION`, `httpOnly`, `SameSite=Strict`, `Secure` (off only with `CALLVERSE_COOKIE_SECURE=false` for plain localhost), **30 minutes, renewed on activity**; new session id at sign-in (against session fixation); in-memory store (one instance; Redis would be needed for several) |
| CSRF | `access.guard.ts` | every request that is not GET, HEAD or OPTIONS needs the session's token, sent as `_csrf` in the form or `X-CSRF-Token` in a header, compared with `timingSafeEqual` |
| Roles | `access.guard.ts` | one global guard: not signed in goes to `/login`; `@Roles(...)` lists the allowed roles, ADMIN always passes; `@Public()` marks the login page |
| Content security policy | `setup.ts` (helmet) | `default-src 'self'`, scripts, styles, fonts only from the app itself, images `self` and `data:`, media `self` and `blob:` (the neural voice), no objects, no framing (`frame-ancestors 'none'`), forms only to the app; **no inline script or style anywhere** |
| Other headers | `setup.ts` | HSTS one year with subdomains, `X-Frame-Options: DENY`, referrer policy `strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(self), geolocation=(), payment=()`, `X-Powered-By` removed |
| Input limits | controllers, `setup.ts` | raw audio bodies capped at **11 MB** (`/quality/audio`), **6 MB** (`/voice/transcribe`), **15 MB** (`/call-review/analyze`); every text field checked for type, length and control characters (`\p{Cc}` replaced by spaces); enumerations checked with `Object.hasOwn` |
| Errors | `errors.filter.ts` | friendly pages (400, 403, 404, 500, 503); details go to the log, never to the browser; an unknown address for a signed-out visitor goes to the login |
| Static files | `setup.ts` | served before sessions (no cookie created), cached 7 days; the `asset()` helper adds a content hash so a changed file is always fetched again |

Honest limits of the security: the accounts share one demo password and live in code (a real deployment would use a database or an identity server such as Keycloak); sessions are lost on restart; there is no rate limit apart from the sign-in lock; the agents service itself has **no authentication** (it is meant to be reachable only from the web app, on the same machine or network).

## Interface features (browser script `app/client/app.ts`)
* **Light and dark theme**, cross-faded, remembered in the browser; an optional **particles** background (on by default, one button turns it off, off automatically for people who ask for reduced motion).
* **Command palette** (`Ctrl/Cmd + K`): type to jump to any page your role may open. **Keyboard shortcuts window** (`?`, closed with `Esc`; ignored while typing in a field).
* **Demo tour**: a guided walk of one customer story from the home page through the workspaces to the presentation mode; the step is kept for the tab only (`sessionStorage`), with Back, Next and End tour.
* **Presentation mode** (`/present`): full-screen slides built from the same data as the ideas page; arrow keys to move, `N` for speaker notes, `F` for full screen, live-demo buttons.
* **Polish**: cards below the fold fade up, figures count up to their value, sidebar names slide out on hover when the rail is collapsed.
* **Per-page behaviour**: live call, voice notes and spoken replies, recording and sample-call upload, reviewer verdict buttons, quality pins on the call timeline, workforce slider, sales reader, the complaint reader (and drag and drop of the demo complaint cards), the training builder. Every browser-side storage use is wrapped so a blocked storage never breaks a page.

## Accessibility
Markup built for keyboard and screen-reader use, an **axe-core audit of every page in both themes** (no violation), a layout that holds on a phone (checked: no horizontal scrolling), reduced motion respected. The script only enhances: the pages work with the server alone, except live calls, voice and uploads.

## Run it
```powershell
cd app
npm ci
npm run build
$env:CALLVERSE_DEMO_PASSWORD = 'demo-password-123'     # at least 12 characters
$env:CALLVERSE_COOKIE_SECURE = 'false'                  # only for http://localhost
$env:AGENTS_MODE = 'http'                               # leave unset for demo data
node dist/main.js                                       # http://localhost:8080
```
With the agents (port 8000) and the emotion service (port 8001) running as described in the [index](README.md). `PORT` and `SESSION_SECRET` are optional. Details on the contract are in `app/README.md`.

## Tests
* **Unit and HTTP tests** (`npm test`, Node's test runner and supertest; the count per branch is in the table of the index): `security-and-pages` (sign-in, lock, CSRF, roles, headers, error pages), `deck-and-simulator` (client simulator, presentation pages), `insights`, `customer` (customer 360, suggestions, the simulator hearing a raised voice), `polish` (pages, validation, accessibility landmarks), `call-review`, `live-call`, `voice`, `workforce` (and the training coach flow), `quality`, `sales`, `complaints`, `training`. They run in demo mode, with a fake or the mock gateway, so they need no Python.
* **Continuous integration** (`.github/workflows/ci.yml`, on every push to main and every pull request): job *web* (Node 24, `npm ci`, `npm run build`, `npm test`) and job *agents* (Python 3.11, `pip install -r requirements.txt`, `pytest -q`, without the heavy speech and emotion models, whose tests skip). The browser tests run on a developer machine, not in CI.

## Honest limits
Demo accounts and password; in-memory sessions; with no agents running, the Training and Complaint pages show fixed demo data ([06](06-training-and-complaints.md)); the client simulator page is a rule-based twin of the Python one; the browser tests need the three services and Edge; the pages are in English only; the `/insights` statistics are synthetic and exist for the presentation (the file says how to remove them).

## Files
`app/src/main.ts`, `setup.ts`, `app.module.ts`, `errors.filter.ts`; `auth/` (`access.guard.ts`, `auth.controller.ts`, `auth.service.ts`); `agents/` (`agent.gateway.ts`, `mock.gateway.ts`, `http.gateway.ts`, `models.ts`); `pages/` (`pages.controller.ts`, `deck.controller.ts`, `live-call.controller.ts`, `quality.controller.ts`, `sales.controller.ts`, `call-review.controller.ts`, `voice.controller.ts`, `client-simulator.ts`, `customer-llm.ts`, `insights.ts`, `charts.ts`, `deck-content.ts`); `app/views/*.njk`; `app/client/app.ts`; `app/public/`; `app/test/`; `app/e2e/`; `.github/workflows/ci.yml`.
