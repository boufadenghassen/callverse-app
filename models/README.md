# models/

Trained models the app will load later (for example `emotion_v3_full.joblib`, or an `.h5` file).
This is the only folder where model files are allowed in git; everywhere else they are ignored.

* Name files `<task>_<version>.<ext>` and add a small `<same name>.json` next to each one:
  dataset, notebook version, metrics and date, so nobody has to guess what a file is.
* GitHub refuses files over 100 MB. For bigger models use Git LFS (`git lfs track "models/*.h5"`) or a GitHub Release.
* Train in `notebooks/`, then copy the finished file here. The notebooks write to `../models` by default.

## Emotion service (used by the app's Call review page)

`src/serve.py` wraps the recommended model (`registry/emotion_wavlm_ft_full_aug2.pt`) in a small FastAPI service.
Start it from the repo root, then open the app as Nour (quality) or admin, page **Call review (AI)**:

```
..\venv\Scripts\python.exe -m uvicorn serve:app --app-dir models/src --port 8001
```

`POST /emotion/analyze` takes the raw audio file and returns the emotion, confidence, mood 0-100, all six probabilities and a
3-second-window timeline. The app finds the service through `CALLVERSE_EMOTION_URL` (default `http://localhost:8001`).
