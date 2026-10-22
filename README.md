# orqestra

A digital twin of a contact center: seven personas, one agent each (client simulator, advisor, workforce manager,
quality analyst, training lead, complaint manager, sales). Student project.

| Folder | What it holds | In git? |
|---|---|---|
| [`app`](app) | The web interface: NestJS server, server-rendered pages, browser script (all TypeScript). Runs with built-in demo data, or with the real agents (`AGENTS_MODE=http`). | yes |
| [`models`](models) | Trained model files the app will load later (`.joblib`, `.h5`, ...). | yes |
| `notebooks` | Jupyter notebooks for speech-emotion training. | **no, pushed empty** |
| `datasets` | CREMA-D and RAVDESS audio. | **no, pushed empty** |

Also: [`docs/agents`](docs/agents/README.md) (documentation of every agent: what was built, how it works, how to run and test it), [`docs/PRESENTATION_FACTS.md`](docs/PRESENTATION_FACTS.md) and [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) (the facts behind the presentation, the demo script), [`ARCHITECTURE.md`](ARCHITECTURE.md) (how the pieces fit and what to build next), [`MLOPS.md`](MLOPS.md) (the model pipeline), [`DATA_COLLECTION.md`](DATA_COLLECTION.md) (recording and labelling real calls, plus where to find public data) and `.github/workflows/ci.yml`
(builds and tests the app on every push).

## Run everything (Windows)

Double-click `start-all.bat` (or run `.\start-all.ps1`). It builds the web app and starts the agents (port 8000), the emotion model (8001) and the web app (8080), waits until they answer, and prints the accounts.
`start-all.bat -Clean` first starts from the clean demo state (rehearsal data is moved to a backup folder, not deleted); `-Reset` only restarts the clock of the complaint cases; `-Stop` stops everything.
It needs Node.js 22+ and the Python environment `..\venv`. For the presentation: [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) and [`docs/PRESENTATION_FACTS.md`](docs/PRESENTATION_FACTS.md).

## Run the web app alone (demo data, no agents)

Needs Node.js 22 or newer.

```bash
cd app
npm ci
npm run build
CALLVERSE_DEMO_PASSWORD=choose-a-long-password CALLVERSE_COOKIE_SECURE=false npm start
```

Open http://localhost:8080 and sign in as `admin` (sees everything), `yasmine`, `karim`, `sana`, `nour`, `amine`,
`rim` or `leila`. On Windows, `app/start-demo.bat` does all of this. More in [`app/README.md`](app/README.md).

## Notebooks and datasets (local only)

These two folders are in the repository so the layout is the same on every machine, but their contents are ignored by
git. Each person keeps their own copies.

Datasets go in `datasets/`:

```
datasets/
  CREMA-D/     clone of https://github.com/CheyneyComputerScience/CREMA-D  (run `git lfs pull` for the real audio)
    AudioWAV/*.wav, VideoDemographics.csv
  RAVDESS/     speech part of the Ryerson Audio-Visual Database of Emotional Speech and Song
    Actor_01/ ... Actor_24/
```

Already downloaded elsewhere? Link instead of copying (Windows, no admin needed):

```bat
mklink /J datasets\CREMA-D "D:\path\to\CREMA-D"
mklink /J datasets\RAVDESS "D:\path\to\folder-that-contains-Actor_01"
```

Notebooks read the data from `CALLVERSE_DATA` (default `../datasets`) and write trained models to `../models`.
Licences: CREMA-D is ODbL, RAVDESS is CC BY-NC-SA 4.0 (non-commercial). Never commit audio or embeddings.

## Working together

* `main` stays green: CI must pass.
* Work on a branch, open a pull request, get one review.
* Trained models: only into `models/`, with a small `.json` note next to each (see `models/README.md`).
