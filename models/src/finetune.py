"""Fine-tune WavLM for 6-class speech emotion recognition on CREMA-D + RAVDESS.

Uses exactly the same actor-wise train/val/test split as notebooks/emotion_v3_improved.ipynb (seed 42), so the test
numbers are comparable with the frozen-embedding result (CREMA-D test accuracy 0.772, RAVDESS 0.727 when both datasets are
trained together). Only the validation actors choose the best epoch; the test actors are scored once, at the end.

    python models/src/finetune.py --quick --epochs 1     # smoke test, a few minutes
    python models/src/finetune.py                         # full run on the GPU
    python models/src/finetune.py --resume                # continue after an interruption (a checkpoint is saved every epoch)

Data comes from CALLVERSE_DATA (default <repo>/datasets). Outputs: models/registry (weights, git-ignored because large),
models/reports (metrics json and predictions csv), models/cache (decoded audio, git-ignored).
"""
import argparse, hashlib, json, math, os, time, warnings
from pathlib import Path

import joblib
import librosa
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from joblib import Parallel, delayed
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

warnings.filterwarnings("ignore", category=UserWarning)
import degrade  # noqa: E402  (same folder)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODELS = HERE.parent
SR = 16000
EMOS = ["ANG", "DIS", "FEA", "HAP", "NEU", "SAD"]          # alphabetical, same order as scikit-learn's classes_
NAMES = {"ANG": "anger", "DIS": "disgust", "FEA": "fear", "HAP": "happy", "NEU": "neutral", "SAD": "sad"}
MOOD = {"ANG": 10, "DIS": 25, "FEA": 30, "SAD": 35, "NEU": 55, "HAP": 90}
FROZEN_BASELINE = {"CREMA-D test accuracy": 0.772, "CREMA-D test macro F1": 0.773, "RAVDESS test accuracy": 0.727,
                   "note": "frozen WavLM layers 5+7+6 concatenated + logistic regression, trained on both datasets (notebook section 9)"}


# ---------------------------------------------------------------------------------------------- data
def build_table(data_dir: Path, quick: bool, seed: int) -> pd.DataFrame:
    """The clips table and the actor split, identical to the notebook."""
    crema_dir, crema = data_dir / "CREMA-D", data_dir / "CREMA-D" / "AudioWAV"
    rav_files = sorted((data_dir / "RAVDESS").glob("Actor_*/*.wav"))
    assert crema.exists() and rav_files, f"datasets not found under {data_dir} (see data README in the repo root)"
    letter_levels = {"LO": "low", "MD": "medium", "HI": "high", "XX": "unspecified"}
    rav_emotion = {"01": "NEU", "02": "CALM", "03": "HAP", "04": "SAD", "05": "ANG", "06": "FEA", "07": "DIS", "08": "SURPRISED"}
    cols = ["dataset", "file", "actor", "emotion", "level", "sex", "age"]

    c = pd.DataFrame({"file": sorted(crema.glob("*.wav"))})
    p = c.file.map(lambda x: x.stem.split("_"))
    c["dataset"], c["actor_num"], c["actor"] = "CREMA-D", p.str[0].astype(int), "C" + p.str[0]
    c["emotion"], c["level"] = p.str[2], p.str[3].map(letter_levels)
    demo = pd.read_csv(crema_dir / "VideoDemographics.csv").rename(columns={"ActorID": "actor_num", "Sex": "sex", "Age": "age"})
    c = c.merge(demo[["actor_num", "sex", "age"]], on="actor_num", how="left")

    r = pd.DataFrame({"file": rav_files})
    q = r.file.map(lambda x: x.stem.split("-"))
    r["dataset"], r["actor"] = "RAVDESS", "R" + q.str[6]
    r["emotion"] = q.str[2].map(rav_emotion)
    r["level"] = q.str[3].map({"01": "normal", "02": "strong"})
    r["sex"] = np.where(q.str[6].astype(int) % 2 == 1, "Male", "Female")
    r["age"] = np.nan
    r = r[r.emotion.isin(EMOS)]
    clips = pd.concat([c[cols], r[cols]], ignore_index=True)

    if quick:
        data = pd.concat([clips[clips.dataset == "CREMA-D"].sample(1500, random_state=seed),
                          clips[clips.dataset == "RAVDESS"].sample(600, random_state=seed)], ignore_index=True)
    else:
        data = clips.copy()
    data["split"] = "train"
    rng = np.random.default_rng(seed)
    for _, g in data.groupby("dataset"):
        a = g.actor.unique().copy(); rng.shuffle(a); n = len(a)
        test_a, val_a = set(a[: int(.15 * n)]), set(a[int(.15 * n): int(.30 * n)])
        data.loc[g.index[g.actor.isin(test_a)], "split"] = "test"
        data.loc[g.index[g.actor.isin(val_a)], "split"] = "val"
    by = data.groupby("split").actor.agg(set)
    assert not (by["train"] & by["val"]) and not (by["train"] & by["test"]) and not (by["val"] & by["test"]), "actor leak between splits"
    return data


def load_clean(path):
    y, _ = librosa.load(path, sr=SR, mono=True)
    y, _ = librosa.effects.trim(y, top_db=30)
    peak = float(np.abs(y).max()) if y.size else 0.0
    return None if peak < 0.005 else (y / peak * 0.95).astype(np.float16)     # silent clips are dropped, as in the notebook


def load_waves(data: pd.DataFrame, cache_dir: Path, tag: str):
    key = hashlib.md5("".join(f"{d}/{p.name}" for d, p in zip(data.dataset, data.file)).encode()).hexdigest()[:8]
    f = cache_dir / f"waves_{tag}_{key}.joblib"
    if f.exists():
        return joblib.load(f)
    t = time.time()
    waves = Parallel(n_jobs=-1)(delayed(load_clean)(p) for p in data.file)
    print(f"decoded {len(waves):,} clips in {time.time() - t:.0f}s")
    cache_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(waves, f)
    return waves


# ---------------------------------------------------------------------------------------------- augmentation
def phone_line(w: torch.Tensor) -> torch.Tensor:
    """Telephone-like band limit, roughly 300 Hz to 3.4 kHz (an approximation with moving averages)."""
    hp = w - F.avg_pool1d(F.pad(w[None, None], (26, 26), mode="reflect"), 53, 1)[0, 0, : w.numel()]
    return F.avg_pool1d(F.pad(hp[None, None], (2, 1), mode="reflect"), 4, 1)[0, 0, : w.numel()]


def add_noise(w: torch.Tensor, snr_db: float, g: torch.Generator) -> torch.Tensor:
    rms = w.pow(2).mean().sqrt().clamp_min(1e-6)
    return w + torch.randn(w.shape, generator=g).to(w.device) * rms / 10 ** (snr_db / 20)


def augment(w: torch.Tensor, g: torch.Generator) -> torch.Tensor:
    """Cheap on-GPU augmentation of one waveform (1-D, peak ~0.95): gain, speed/pitch, phone-line band limit, noise."""
    u = lambda lo, hi: lo + (hi - lo) * torch.rand((), generator=g).item()
    w = w * 10 ** (u(-6, 6) / 20)
    if torch.rand((), generator=g) < 0.3:                                         # speed + pitch change, 0.9x to 1.1x
        w = F.interpolate(w[None, None], size=max(1600, int(w.numel() / u(0.9, 1.1))), mode="linear", align_corners=False)[0, 0]
    if torch.rand((), generator=g) < 0.3:
        w = phone_line(w)
    if torch.rand((), generator=g) < 0.5:                                         # background noise, 15 to 35 dB signal-to-noise
        w = add_noise(w, u(15, 35), g)
    return w / w.abs().max().clamp_min(1e-6) * 0.95


CODEC_NAMES = list(degrade.CODECS)


def _codec_copies(j, w16, per_clip):
    rng = np.random.default_rng(10_000 + int(j))
    names = rng.choice(CODEC_NAMES, per_clip, replace=False)
    w = w16.astype(np.float32)
    return int(j), [degrade.codec_roundtrip(w, str(n)).astype(np.float16) for n in names]


def build_codec_cache(waves, idx, cache_dir: Path, tag: str, per_clip: int = 2):
    """Real-codec copies of every training clip (two random codecs each), made once with ffmpeg and cached."""
    key = hashlib.md5(("".join(map(str, idx[:50])) + str(len(idx)) + str(per_clip)).encode()).hexdigest()[:8]
    f = cache_dir / f"codecs_{tag}_{key}.joblib"
    if f.exists():
        return joblib.load(f)
    t = time.time()

    out = dict(Parallel(n_jobs=-1)(delayed(_codec_copies)(j, waves[j], per_clip) for j in idx))
    print(f"made {per_clip} codec copies of {len(idx):,} training clips in {time.time() - t:.0f}s")
    joblib.dump(out, f)
    return out


def augment_v2(w: np.ndarray, codec_copies, pool, rng: np.random.Generator) -> np.ndarray:
    """Call-center-like augmentation on one float32 waveform: real codec, room, babble/hum/white noise, packet loss, gain, speed."""
    if codec_copies and rng.random() < 0.4:
        w = codec_copies[int(rng.integers(len(codec_copies)))].astype(np.float32)
    w = w * 10 ** (rng.uniform(-6, 6) / 20)
    if rng.random() < 0.25:                                                        # speed + pitch, 0.9x to 1.1x
        n = max(1600, int(len(w) / rng.uniform(0.9, 1.1)))
        w = np.interp(np.linspace(0, len(w) - 1, n), np.arange(len(w)), w).astype(np.float32)
    if rng.random() < 0.25:
        w = degrade.reverb(w, rng.uniform(0.2, 0.6), rng)
    if rng.random() < 0.7:                                                         # background: white 10-35 dB, babble 3-20 dB, mains hum 8-30 dB
        kind = rng.choice(["white", "babble", "hum"], p=[0.35, 0.45, 0.20])
        if kind == "white":
            w = degrade.add_at_snr(w, rng.standard_normal(len(w)).astype(np.float32), rng.uniform(10, 35))
        elif kind == "babble":
            w = degrade.add_at_snr(w, degrade.babble(pool, len(w), rng), rng.uniform(3, 20))
        else:
            w = degrade.add_at_snr(w, degrade.hum(len(w), float(rng.choice([50.0, 100.0])), rng), rng.uniform(8, 30))
    if rng.random() < 0.12:
        w = degrade.packet_loss(w, rng)
    return degrade.finish(w)


# ---------------------------------------------------------------------------------------------- model
class Net(nn.Module):
    """WavLM encoder (CNN feature extractor frozen, transformer trained) + learned weighted sum of all layers + small head."""

    def __init__(self, name: str, dropout: float):
        super().__init__()
        from transformers import WavLMModel
        self.enc = WavLMModel.from_pretrained(name)
        self.enc.config.layerdrop = 0.0                 # layer-drop would skip layers and break the layer weighting below
        self.enc.freeze_feature_encoder()
        layers, dim = self.enc.config.num_hidden_layers + 1, self.enc.config.hidden_size
        self.layer_w = nn.Parameter(torch.zeros(layers))
        self.head = nn.Sequential(nn.LayerNorm(dim), nn.Dropout(dropout), nn.Linear(dim, 256), nn.GELU(), nn.Dropout(dropout), nn.Linear(256, len(EMOS)))

    def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        hs = torch.stack(self.enc(x, output_hidden_states=True).hidden_states)    # (layers, batch, frames, dim)
        h = (torch.softmax(self.layer_w, 0)[:, None, None, None] * hs).sum(0)
        frames = self.enc._get_feat_extract_output_lengths(lengths)
        mask = (torch.arange(h.shape[1], device=h.device)[None] < frames[:, None]).to(h.dtype)    # ignore the zero padding
        return self.head((h * mask[..., None]).sum(1) / mask.sum(1, keepdim=True).clamp_min(1))


def pad(waves, device):
    lengths = torch.tensor([len(w) for w in waves], device=device)
    x = torch.zeros(len(waves), int(lengths.max()), device=device)
    for i, w in enumerate(waves):
        x[i, : len(w)] = w
    return x, lengths


def batches(order, lengths, size):
    """Groups clips of similar length so padding stays small."""
    for i in range(0, len(order), size * 50):
        block = sorted(order[i:i + size * 50], key=lambda j: lengths[j])
        yield from (block[k:k + size] for k in range(0, len(block), size))


@torch.no_grad()
def predict(model, waves, idx, device, size=32):
    model.eval()
    out = np.zeros((len(idx), len(EMOS)), np.float32)
    pos = {j: k for k, j in enumerate(idx)}
    for b in batches(list(idx), [len(w) for w in waves], size):
        x, ln = pad([torch.from_numpy(waves[j].astype(np.float32)).to(device) for j in b], device)
        with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            p = torch.softmax(model(x, ln).float(), -1)
        for j, row in zip(b, p.cpu().numpy()):
            out[pos[j]] = row
    return out


# ---------------------------------------------------------------------------------------------- evaluation
def report(data: pd.DataFrame, y_true, proba, test_mask) -> dict:
    pred = np.array(EMOS)[proba.argmax(1)]
    d = data[test_mask].reset_index(drop=True)
    res = {"overall": {"clips": int(len(d)), "accuracy": accuracy_score(y_true, pred), "macro_f1": f1_score(y_true, pred, average="macro")}}
    for ds in ("CREMA-D", "RAVDESS"):
        m = (d.dataset == ds).values
        res[ds] = {"clips": int(m.sum()), "accuracy": accuracy_score(y_true[m], pred[m]), "macro_f1": f1_score(y_true[m], pred[m], average="macro")}
    res["per_emotion_recall"] = {NAMES[e]: float(((pred == e) & (y_true == e)).sum() / max((y_true == e).sum(), 1)) for e in EMOS}
    res["confusion_matrix"] = {"labels": [NAMES[e] for e in EMOS], "rows_true_cols_pred": confusion_matrix(y_true, pred, labels=EMOS).tolist()}
    cd = (d.dataset == "CREMA-D").values
    ok = (pred == y_true)
    res["CREMA-D_by_sex"] = {s: float(ok[cd & (d.sex == s).values].mean()) for s in ("Female", "Male") if (cd & (d.sex == s).values).any()}
    bands = pd.cut(d.age, [0, 25, 35, 50, 120], labels=["18-25", "26-35", "36-50", "51+"])
    res["CREMA-D_by_age_band"] = {str(b): {"accuracy": float(ok[cd & (bands == b).values].mean()), "clips": int((cd & (bands == b).values).sum())}
                                  for b in bands.cat.categories if (cd & (bands == b).values).any()}
    # 95% confidence interval for CREMA-D test accuracy, resampling ACTORS (clips of one actor are not independent)
    rng = np.random.default_rng(0)
    actors = d[cd].actor.unique()
    per = {a: (int(ok[cd & (d.actor == a).values].sum()), int((cd & (d.actor == a).values).sum())) for a in actors}
    boots = []
    for _ in range(2000):
        s = rng.choice(actors, len(actors))
        boots.append(sum(per[a][0] for a in s) / sum(per[a][1] for a in s))
    res["CREMA-D"]["accuracy_ci95"] = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]
    res["CREMA-D"]["test_actors"] = int(len(actors))
    return res


# ---------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="1,500 CREMA-D + 600 RAVDESS clips (same subset as the notebook's quick mode)")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-5, help="learning rate of the WavLM transformer")
    ap.add_argument("--head-lr", type=float, default=1e-3, help="learning rate of the layer weights and the head")
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--patience", type=int, default=3, help="stop after this many epochs without a better validation macro-F1")
    ap.add_argument("--aug", choices=["none", "v1", "v2"], default="v1",
                    help="none; v1 = gain/speed/phone band-limit/white noise; v2 = call-center-like: real codecs, babble, hum, reverb, packet loss")
    ap.add_argument("--no-aug", action="store_true", help="same as --aug none")
    ap.add_argument("--model", default="microsoft/wavlm-base-plus")
    ap.add_argument("--seed", type=int, default=42, help="training randomness (initial head, batch order, augmentation)")
    ap.add_argument("--split-seed", type=int, default=42, help="which actors are train/val/test; keep 42 to stay comparable with the notebook")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--data", default=os.environ.get("CALLVERSE_DATA", str(ROOT / "datasets")))
    a = ap.parse_args()

    if a.no_aug:
        a.aug = "none"
    tag = a.tag or ("quick" if a.quick else "full") + {"none": "_noaug", "v1": "", "v2": "_aug2"}[a.aug]
    cache, registry, reports = MODELS / "cache", MODELS / "registry", MODELS / "reports"
    for d in (cache, registry, reports):
        d.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(a.seed); np.random.seed(a.seed)
    print(f"device: {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'cpu: this will be very slow'}) | run: {tag}")

    data = build_table(Path(a.data), a.quick, a.split_seed)
    waves = load_waves(data, cache, "quick" if a.quick else "full")
    keep = np.array([w is not None for w in waves])
    if not keep.all():
        print("dropped silent clips:", [f"{d}/{p.name}" for d, p, k in zip(data.dataset, data.file, keep) if not k])
    data = data[keep].reset_index(drop=True)
    waves = [w for w in waves if w is not None]
    y = data.emotion.values
    yi = np.array([EMOS.index(e) for e in y])
    tr, va, te = (np.where(data.split == s)[0] for s in ("train", "val", "test"))
    print(f"{len(data):,} clips | train {len(tr):,} | val {len(va):,} | test {len(te):,}")
    lengths = [len(w) for w in waves]

    codec_copies, pool, np_rng = None, None, np.random.default_rng(a.seed + 7)
    if a.aug == "v2":
        codec_copies = build_codec_cache(waves, list(tr), cache, "quick" if a.quick else "full")
        pool = [waves[j] for j in tr]                      # babble is made from training speakers only

    model = Net(a.model, a.dropout).to(device)
    enc_params = [p for n, p in model.enc.named_parameters() if p.requires_grad]
    opt = torch.optim.AdamW([{"params": enc_params, "lr": a.lr}, {"params": [model.layer_w, *model.head.parameters()], "lr": a.head_lr}], weight_decay=0.01)
    steps_per_epoch = math.ceil(len(tr) / a.batch)
    total, warm = steps_per_epoch * a.epochs, max(1, int(0.1 * steps_per_epoch * a.epochs))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: (s + 1) / warm if s < warm else max(0.0, 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total - warm)))))

    ckpt_path, best_path = registry / f"ckpt_{tag}.pt", registry / f"emotion_wavlm_ft_{tag}.pt"
    history, best_f1, start_epoch, bad = [], -1.0, 0, 0
    if a.resume and ckpt_path.exists():
        ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        model.load_state_dict(ck["model"]); opt.load_state_dict(ck["opt"]); sched.load_state_dict(ck["sched"])
        history, best_f1, start_epoch, bad = ck["history"], ck["best_f1"], ck["epoch"] + 1, ck["bad"]
        print(f"resumed after epoch {ck['epoch'] + 1}, best validation macro-F1 so far {best_f1:.4f}")

    g = torch.Generator().manual_seed(a.seed)
    max_len = 6 * SR
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    for epoch in range(start_epoch, a.epochs):
        model.train()
        t0, run_loss, seen = time.time(), 0.0, 0
        order = list(np.random.default_rng(a.seed + epoch).permutation(tr))
        bl = list(batches(order, lengths, a.batch))
        np.random.default_rng(a.seed + 1000 + epoch).shuffle(bl)
        for b in bl:
            ws = []
            for j in b:
                if a.aug == "v2":
                    arr = augment_v2(waves[j].astype(np.float32), [] if codec_copies is None else codec_copies.get(int(j), []), pool, np_rng)
                    w = torch.from_numpy(arr).to(device)
                else:
                    w = torch.from_numpy(waves[j].astype(np.float32)).to(device)
                if w.numel() > max_len:
                    s = int(torch.randint(0, w.numel() - max_len + 1, (1,), generator=g)); w = w[s:s + max_len]
                ws.append(w if a.aug != "v1" else augment(w, g))
            x, ln = pad(ws, device)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits = model(x, ln)
            loss = loss_fn(logits.float(), torch.tensor(yi[b], device=device))
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step()
            run_loss += loss.item() * len(b); seen += len(b)
        pv = predict(model, waves, va, device)
        vf1 = f1_score(y[va], np.array(EMOS)[pv.argmax(1)], average="macro")
        vacc = accuracy_score(y[va], np.array(EMOS)[pv.argmax(1)])
        history.append({"epoch": epoch + 1, "train_loss": run_loss / seen, "val_macro_f1": vf1, "val_accuracy": vacc, "seconds": time.time() - t0})
        print(f"epoch {epoch + 1}/{a.epochs} | loss {run_loss / seen:.4f} | val macro-F1 {vf1:.4f} acc {vacc:.4f} | {time.time() - t0:.0f}s"
              + (f" | peak GPU {torch.cuda.max_memory_allocated() / 1e9:.1f} GB" if device.type == "cuda" else ""), flush=True)
        if vf1 > best_f1:
            best_f1, bad = vf1, 0
            torch.save({"model": model.state_dict(), "emos": EMOS, "base_model": a.model, "args": vars(a), "epoch": epoch + 1, "val_macro_f1": vf1}, best_path)
        else:
            bad += 1
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "epoch": epoch, "best_f1": best_f1, "history": history, "bad": bad}, ckpt_path)
        if bad >= a.patience:
            print(f"no improvement for {a.patience} epochs: stopping early")
            break

    # the test actors are scored once, with the epoch the validation actors liked best
    model.load_state_dict(torch.load(best_path, map_location="cpu", weights_only=False)["model"])
    pt = predict(model, waves, te, device)
    res = report(data, y[te], pt, (data.split == "test").values)
    res.update({"run": tag, "best_validation_macro_f1": best_f1, "history": history, "params": vars(a), "frozen_baseline_for_comparison": FROZEN_BASELINE,
                "finished": time.strftime("%Y-%m-%d %H:%M")})
    (reports / f"finetune_{tag}.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    pd.DataFrame({"file": data.file[te].map(lambda p: p.name), "dataset": data.dataset[te], "actor": data.actor[te], "true": y[te],
                  "pred": np.array(EMOS)[pt.argmax(1)], **{f"p_{NAMES[e]}": pt[:, i] for i, e in enumerate(EMOS)}}).to_csv(reports / f"finetune_{tag}_test_predictions.csv", index=False)

    c, r = res["CREMA-D"], res["RAVDESS"]
    print("\n=== test actors (scored once) ===")
    print(f"CREMA-D  accuracy {c['accuracy']:.3f} (95% CI {c['accuracy_ci95'][0]:.3f} to {c['accuracy_ci95'][1]:.3f}) | macro-F1 {c['macro_f1']:.3f}   [frozen baseline 0.772 / 0.773]")
    print(f"RAVDESS  accuracy {r['accuracy']:.3f} | macro-F1 {r['macro_f1']:.3f}   [frozen baseline 0.727]")
    print("per-emotion recall:", {k: round(v, 3) for k, v in res["per_emotion_recall"].items()})
    print("CREMA-D by sex:", {k: round(v, 3) for k, v in res["CREMA-D_by_sex"].items()})
    print("CREMA-D by age band:", {k: (round(v["accuracy"], 3), v["clips"]) for k, v in res["CREMA-D_by_age_band"].items()})
    print(f"saved {best_path.name} and reports/finetune_{tag}.json")


if __name__ == "__main__":
    main()
