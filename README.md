# CallVerse

A digital twin of a contact center: seven personas, one agent each (client simulator, advisor, workforce manager,
quality analyst, training lead, complaint manager, sales). Student project.

| Folder | What it holds | In git? |
|---|---|---|
| [`app`](app) | The web interface: NestJS server, server-rendered pages, browser script (all TypeScript). Runs today with mock agent data. | yes |
| [`models`](models) | Trained model files the app will load later (`.joblib`, `.h5`, ...). | yes |
| `notebooks` | Jupyter notebooks for speech-emotion training. | **no, pushed empty** |
| `datasets` | CREMA-D and RAVDESS audio. | **no, pushed empty** |

Also: [`ARCHITECTURE.md`](ARCHITECTURE.md) (how the pieces fit and what to build next) and `.github/workflows/ci.yml`
(builds and tests the app on every push).

## Run the web app

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
