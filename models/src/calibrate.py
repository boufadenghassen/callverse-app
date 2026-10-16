"""Temperature scaling: makes the model's confidence match how often it is right.

Run from the repo root:  ../venv/Scripts/python.exe models/src/calibrate.py
One number T is fitted on the validation actors (never trained on) and divides the model's raw scores before the softmax.
The predicted emotion never changes; only the percentages do. Test actors are used once, to check the result.
Writes models/emotion_wavlm_ft_full_aug2_calibration.json, which serve.py reads.
"""
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

import finetune as ft

WEIGHTS = ft.MODELS / "registry" / "emotion_wavlm_ft_full_aug2.pt"
OUT = ft.MODELS / "emotion_wavlm_ft_full_aug2_calibration.json"


@torch.no_grad()
def logits_of(model, waves, idx, device):
    model.eval()
    out = np.zeros((len(idx), len(ft.EMOS)), np.float32)
    pos = {j: k for k, j in enumerate(idx)}
    for b in ft.batches(list(idx), [len(w) for w in waves], 8):
        x, ln = ft.pad([torch.from_numpy(waves[j].astype(np.float32)).to(device) for j in b], device)
        with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            z = model(x, ln).float()
        for j, row in zip(b, z.cpu().numpy()):
            out[pos[j]] = row
    return out


def ece(p, y, bins=10):
    """Expected calibration error: average gap between confidence and accuracy, over confidence bins."""
    conf, hit = p.max(1), p.argmax(1) == y
    edges = np.linspace(0, 1, bins + 1)
    gap = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            gap += m.mean() * abs(conf[m].mean() - hit[m].mean())
    return float(gap)


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ck = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
    model = ft.Net(ck["base_model"], 0.0)
    model.load_state_dict(ck["model"])
    model.to(device)

    data = ft.build_table(ft.ROOT / "datasets", False, 42)
    waves = ft.load_waves(data, ft.MODELS / "cache", "full")
    keep = np.array([w is not None for w in waves])
    data = data[keep].reset_index(drop=True)
    waves = [w for w in waves if w is not None]
    y = np.array([ft.EMOS.index(e) for e in data.emotion])
    va, te = (np.where(data.split == s)[0] for s in ("val", "test"))

    zv, zt = logits_of(model, waves, va, device), logits_of(model, waves, te, device)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)
    zv_t, yv_t = torch.from_numpy(zv), torch.from_numpy(y[va])

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(zv_t / log_t.exp(), yv_t)
        loss.backward()
        return loss
    opt.step(closure)
    T = float(log_t.exp())

    soft = lambda z, t=1.0: torch.softmax(torch.from_numpy(z) / t, 1).numpy()
    res = {"temperature": round(T, 3), "fitted_on": f"{len(va)} validation clips", "checked_on": f"{len(te)} test clips (unseen actors)"}
    for name, t in (("before", 1.0), ("after", T)):
        p = soft(zt, t)
        res[name] = {"ECE": round(ece(p, y[te]), 3), "mean_confidence": round(float(p.max(1).mean()), 3),
                     "accuracy": round(float((p.argmax(1) == y[te]).mean()), 3),
                     "NLL": round(float(F.nll_loss(torch.log(torch.from_numpy(p)), torch.from_numpy(y[te]))), 3)}
    OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
