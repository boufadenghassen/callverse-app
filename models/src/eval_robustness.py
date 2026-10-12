"""Does the model still work on call-center-like audio? Scores every model on the SAME test clips under realistic conditions:

  clean                       the studio recording as it is
  AMR-NB, GSM, G.711, Opus    real telephone codecs (through ffmpeg)
  babble 10 dB                several other people talking, 10 dB below the voice
  hum 60 Hz                   mains hum at 60 Hz (training only ever saw 50 and 100 Hz)      <- unseen
  pink noise 10 dB            coloured noise (training only ever saw white, babble and hum)  <- unseen
  reverb 0.5 s                a small echoing room
  packet loss                 a few 20 to 60 ms dropouts
  call mix                    reverb + AMR-NB codec + babble at 15 dB, all together

Models: frozen (WavLM layers 5+7+6 + logistic regression), ft (fine-tuned, augmentation v1), ft_noaug, ft_aug2 (augmentation v2).

    python models/src/eval_robustness.py
"""
import json, sys, time
from pathlib import Path

import numpy as np
import torch
from joblib import Parallel, delayed
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
import degrade  # noqa: E402
import finetune as ft  # noqa: E402

LAYERS = [5, 7, 6]
CS = [0.003, 0.01, 0.03, 0.1, 0.3, 1.0]
MODELS = (("ft", "full"), ("ft_noaug", "full_noaug"), ("ft_aug2", "full_aug2"), ("aug2_seed1", "full_aug2_s1"), ("aug2_seed2", "full_aug2_s2"))


def codecs(ws, name):
    return [w for w in Parallel(n_jobs=-1)(delayed(degrade.codec_roundtrip)(w, name) for w in ws)]


def build_conditions(ws):
    """ws: clean test waveforms (float32). Returns {condition name: list of degraded waveforms}."""
    rngs = [np.random.default_rng(5000 + i) for i in range(len(ws))]
    fin = degrade.finish
    out = {"clean": ws}
    for label, name in (("AMR-NB codec", "amr_nb"), ("GSM codec", "gsm"), ("G.711 mu-law codec", "mulaw"), ("Opus 10 kbps codec", "opus")):
        out[label] = [fin(w) for w in codecs(ws, name)]
    out["babble 10 dB"] = [fin(degrade.add_at_snr(w, degrade.babble(ws, len(w), r), 10)) for w, r in zip(ws, rngs)]
    out["hum 60 Hz 15 dB (unseen)"] = [fin(degrade.add_at_snr(w, degrade.hum(len(w), 60.0, r), 15)) for w, r in zip(ws, rngs)]
    out["pink noise 10 dB (unseen)"] = [fin(degrade.add_at_snr(w, degrade.coloured(len(w), "pink", r), 10)) for w, r in zip(ws, rngs)]
    out["reverb 0.5 s"] = [fin(degrade.reverb(w, 0.5, r)) for w, r in zip(ws, rngs)]
    out["packet loss"] = [fin(degrade.packet_loss(w, r)) for w, r in zip(ws, rngs)]
    rev = [degrade.reverb(w, 0.3, r) for w, r in zip(ws, rngs)]
    out["call mix (reverb+AMR+babble)"] = [fin(degrade.add_at_snr(w, degrade.babble(ws, len(w), r), 15)) for w, r in zip(codecs(rev, "amr_nb"), rngs)]
    return out


@torch.no_grad()
def frozen_features(enc, waves, device):
    out = []
    for w in waves:
        x = torch.from_numpy(np.asarray(w, dtype=np.float32))[None].to(device)
        with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            hs = enc(x, output_hidden_states=True).hidden_states
        out.append(torch.cat([hs[i][0].float().mean(0) for i in LAYERS]).cpu().numpy())
    return np.stack(out)


def load_ft(tag, device):
    path = ft.MODELS / "registry" / f"emotion_wavlm_ft_{tag}.pt"
    if not path.exists():
        return None
    ck = torch.load(path, map_location="cpu", weights_only=False)
    m = ft.Net(ck["base_model"], ck["args"]["dropout"]).to(device)
    m.load_state_dict(ck["model"])
    return m.eval()


def main():
    skip_frozen = "--skip-frozen" in sys.argv     # reuse the frozen row from the last run (its classifier takes ~10 minutes to fit)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = ft.build_table(ft.ROOT / "datasets", quick=False, seed=42)
    waves = ft.load_waves(data, ft.MODELS / "cache", "full")
    keep = np.array([w is not None for w in waves])
    data, waves = data[keep].reset_index(drop=True), [w for w in waves if w is not None]
    y = data.emotion.values
    tr, va, te = (np.where(data.split == s)[0] for s in ("train", "val", "test"))

    t = time.time()
    conds = build_conditions([waves[j].astype(np.float32) for j in te])
    print(f"built {len(conds)} test conditions x {len(te):,} clips in {time.time() - t:.0f}s")

    probas = {}
    prev = ft.MODELS / "reports" / "robustness_v2.json"
    if skip_frozen and prev.exists():
        frozen_rows, best = json.loads(prev.read_text())["accuracy"]["frozen"], json.loads(prev.read_text())["frozen_C"]
    else:
        frozen_rows = None
        from transformers import WavLMModel
        enc = WavLMModel.from_pretrained("microsoft/wavlm-base-plus").to(device).eval()
        Xtr, Xva = frozen_features(enc, [waves[j] for j in tr], device), frozen_features(enc, [waves[j] for j in va], device)
        best = max(CS, key=lambda C: f1_score(y[va], make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=3000)).fit(Xtr, y[tr]).predict(Xva), average="macro"))
        frozen = make_pipeline(StandardScaler(), LogisticRegression(C=best, max_iter=3000)).fit(Xtr, y[tr])
        print(f"frozen classifier: C = {best} (chosen on validation actors)")
        probas["frozen"] = {n: frozen.predict_proba(frozen_features(enc, ws, device)) for n, ws in conds.items()}
        del enc; torch.cuda.empty_cache()
    for name, tag in MODELS:
        model = load_ft(tag, device)
        if model is not None:
            probas[name] = {n: ft.predict(model, ws, list(range(len(ws))), device) for n, ws in conds.items()}
            del model; torch.cuda.empty_cache()

    seeds = [m for m in ("ft_aug2", "aug2_seed1", "aug2_seed2") if m in probas]
    if len(seeds) > 1:                                                  # average the probabilities of the seeds
        probas[f"ensemble of {len(seeds)} seeds"] = {n: np.mean([probas[m][n] for m in seeds], axis=0) for n in conds}
    yt = y[te]
    rows = {m: {c: float(accuracy_score(yt, np.array(ft.EMOS)[p.argmax(1)])) for c, p in by.items()} for m, by in probas.items()}
    if frozen_rows:
        rows = {"frozen": frozen_rows, **rows}
    short = {c: c.split(" (")[0][:15] for c in conds}
    print(f"\ntest accuracy, same {len(te):,} test clips (13 CREMA-D + 3 RAVDESS actors); chance is 16.7%")
    print(f"{'':9s}" + "".join(f"{short[c]:>16s}" for c in conds) + f"{'mean degraded':>16s}")
    for m, by in rows.items():
        deg = [v for c, v in by.items() if c != "clean"]
        print(f"{m:9s}" + "".join(f"{by[c]:>16.3f}" for c in conds) + f"{np.mean(deg):>16.3f}")
    (ft.MODELS / "reports" / "robustness_v3.json").write_text(json.dumps({"frozen_C": best, "test_clips": int(len(te)), "accuracy": rows,
        "conditions": list(conds), "note": "hum 60 Hz and pink noise were never used in any training augmentation; codecs are real (ffmpeg)."}, indent=2), encoding="utf-8")
    print("saved models/reports/robustness_v3.json")


if __name__ == "__main__":
    main()
