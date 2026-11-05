"""Télécharge les voix locales (une seule fois, ~330 Mo au total) depuis GitHub.
   python download_voices.py
Les voix sont des modèles Piper (licence libre) exécutés localement par sherpa-onnx."""
import json, os, sys, tarfile, tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
MODELS = Path(os.getenv("TTS_MODELS_DIR", ROOT / "models" / "tts"))
URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/{name}.tar.bz2"

table = json.loads((ROOT / "data" / "voices.json").read_text(encoding="utf-8"))
names = sorted({v["model"] for v in table.values()})
MODELS.mkdir(parents=True, exist_ok=True)

for name in names:
    dest = MODELS / name
    if dest.exists() and list(dest.glob("*.onnx")):
        print(f"[ok] {name} déjà installé")
        continue
    print(f"[..] téléchargement de {name}")
    with tempfile.NamedTemporaryFile(suffix=".tar.bz2", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        r = requests.get(URL.format(name=name), stream=True, timeout=60)
        r.raise_for_status()
        total, done = int(r.headers.get("content-length", 0)), 0
        for chunk in r.iter_content(1 << 20):
            tmp.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r     {done / 1e6:6.1f} / {total / 1e6:.1f} Mo", end="", flush=True)
    print()
    with tarfile.open(tmp_path, "r:bz2") as tar:
        try:
            tar.extractall(MODELS, filter="data")
        except TypeError:  # Python < 3.12
            tar.extractall(MODELS)
    tmp_path.unlink()
    print(f"[ok] {name} installé")
print(f"\nVoix installées dans {MODELS}")
