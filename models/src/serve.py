"""Emotion service: the fine-tuned WavLM behind one HTTP call, used by the app's Call review page.

Run from the repo root:  ..\venv\Scripts\python.exe -m uvicorn serve:app --app-dir models/src --port 8001
POST /emotion/analyze  body = raw audio file (wav, mp3, ogg, flac...)  ->  JSON, see analyze() below.
"""
import io
import os
from pathlib import Path

import librosa
import numpy as np
import torch
from fastapi import FastAPI, HTTPException, Request

import finetune as ft

WEIGHTS = Path(os.environ.get("EMOTION_WEIGHTS", ft.MODELS / "registry" / "emotion_wavlm_ft_full_aug2.pt"))
WINDOW = 3 * ft.SR          # the model was trained on short acted clips, so long calls are scored in 3 s windows
MAX_SECONDS = 120

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
ck = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
model = ft.Net(ck["base_model"], 0.0)
model.load_state_dict(ck["model"])
model.to(device).eval()

app = FastAPI(title="orqestra emotion service")


@app.get("/health")
def health():
    return {"status": "UP", "model": WEIGHTS.name, "device": device.type}


@app.post("/emotion/analyze")
async def analyze(req: Request):
    raw = await req.body()
    try:
        y, _ = librosa.load(io.BytesIO(raw), sr=ft.SR, mono=True, duration=MAX_SECONDS)
    except Exception:
        raise HTTPException(400, "Could not read this audio file.")
    y, _ = librosa.effects.trim(y, top_db=30)
    peak = float(np.abs(y).max()) if y.size else 0.0
    if peak < 0.005 or len(y) < ft.SR // 2:
        raise HTTPException(400, "The recording is silent or shorter than half a second.")
    y = (y / peak * 0.95).astype(np.float32)           # same loudness handling as training (finetune.load_clean)

    n = max(1, round(len(y) / WINDOW))
    bounds = np.linspace(0, len(y), n + 1).astype(int)
    waves = [y[a:b] for a, b in zip(bounds[:-1], bounds[1:])]
    proba = ft.predict(model, waves, list(range(n)), device)       # (windows, 6)
    whole = proba.mean(0)

    best = int(whole.argmax())
    return {
        "emotion": ft.NAMES[ft.EMOS[best]],
        "confidence": round(float(whole[best]), 3),
        "mood": round(sum(float(p) * ft.MOOD[e] for p, e in zip(whole, ft.EMOS))),     # 0 = furious, 100 = delighted
        "durationSec": round(len(y) / ft.SR, 1),
        "probabilities": {ft.NAMES[e]: round(float(p), 3) for e, p in zip(ft.EMOS, whole)},
        "timeline": [{"startSec": round(a / ft.SR, 1), "emotion": ft.NAMES[ft.EMOS[int(p.argmax())]], "confidence": round(float(p.max()), 3)}
                     for a, p in zip(bounds[:-1], proba)],
        "model": WEIGHTS.name,
    }
