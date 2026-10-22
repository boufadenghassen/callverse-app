# 8. Emotion model (shared): hearing how the customer feels

A speech-emotion model built by the team and served as its own service. It is the only component trained from data. It is used by the **Call review** page (upload a recording, see how the caller felt moment by moment), by the **quality analyst** (the mood of every customer sentence in a recorded call) and by the **live call**: the advisor's voice notes are heard too, so the simulated customer can react to a raised voice.

## What it does
It listens to a clip of speech and answers one of **six emotions**: anger, disgust, fear, happy, neutral, sad, plus a **mood from 0 (furious) to 100 (delighted)**. The mood is the probability-weighted average of a lookup: anger 10, disgust 25, fear 30, sad 35, neutral 55, happy 90.

## Data
* **CREMA-D** (about 7,400 acted clips, 91 actors, ODbL licence) and **RAVDESS** speech (24 actors, CC BY-NC-SA 4.0, non-commercial). RAVDESS's "calm" and "surprised" are left out so both corpora share the six classes. About **8,500 clips** in all.
* **Actor-wise split** (seed 42): per corpus, 15 % of the actors are test, 15 % validation, the rest train, so **no actor appears in two splits** (an assertion checks it): **5,987 train, 1,312 validation, 1,198 test clips (16 test actors)**. Only the validation actors choose the best epoch; the test actors are scored once at the end.
* Audio is trimmed of silence (30 dB), peak-normalised to 0.95 and resampled to 16 kHz. **Datasets are not in git** (size, licences); each person keeps a local copy under `datasets/` (`CALLVERSE_DATA`).

## The model (`models/src/finetune.py`)
* **Backbone**: `microsoft/wavlm-base-plus`; the convolutional front end is **frozen**, the transformer is **fine-tuned**.
* **Head**: a learned softmax weighting of all 13 hidden layers, a masked average over time (padding ignored), then LayerNorm, dropout 0.2, a 256-unit layer with GELU, dropout, and 6 outputs.
* **Training**: AdamW (learning rate 3e-5 for the transformer, 1e-3 for the layer weights and head, weight decay 0.01), batch 16, up to 8 epochs, 10 % warm-up, label smoothing 0.05, early stopping after 3 epochs without a better validation macro-F1. About **13 minutes on an RTX 4060**, plus 4 minutes to prepare the codec copies.
* **Augmentation v2** (the recommended model, `emotion_wavlm_ft_full_aug2.pt`, 361 MB, local only): real telephone codecs through ffmpeg (**AMR-NB, GSM, G.711, Opus**), a synthetic small room, babble made from other training speakers, mains hum, white noise, packet loss, gain and speed. (`degrade.py` builds these effects; v1 was a cheaper on-GPU version.)

## Measured results
| | Clean test | Mean of 10 degraded conditions | Worst |
|---|---|---|---|
| **Fine-tuned WavLM, augmentation v2 (used)** | **73.8 %** (CREMA-D, 95 % interval 68.6 to 79.5; also 73.8 % over all 1,198 test clips), 73.5 % (RAVDESS) | **71.5 %** | 65.3 % (a mix of reverb, codec and babble) |
| Frozen WavLM + logistic regression (baseline) | 76.9 % | 57.5 % | 30.7 % |

* The 10 degraded conditions (`eval_robustness.py`): AMR-NB 72.4 %, GSM 72.3 %, G.711 72.6 %, Opus 72.7 %, babble at 10 dB 73.2 %, 60 Hz hum (never seen in training) 74.7 %, pink noise (never seen) 71.2 %, reverb 0.5 s 68.4 %, packet loss 72.6 %, the call mix 65.3 %.
* **What was traded**: about 3 points of clean accuracy for much better behaviour on call-like audio. **Sad is the weakest class (55 % recall).**
* Other trained variants and seeds are kept in `models/registry/` (local) with their reports in `models/reports/`; each has a small `.json` card next to it (`models/*.json`).

## Calibration (`calibrate.py`)
The raw model is over-confident (80.6 % average confidence for 73.5 % accuracy on the test clips, as recorded in the calibration file). One **temperature T = 1.228** is fitted on the 1,312 validation clips; the service divides the raw scores by T before the softmax. On the test actors the calibration error fell from **0.081 to 0.030**; the predicted emotion never changes. It was calibrated on clean acted speech only, so on real calls the probabilities are probably still too high. *The web pages no longer display the confidence percentages* (the calibration still shapes the numbers behind the mood and the explanation).

## The service (`models/src/serve.py`, port 8001)
`POST /emotion/analyze` takes the raw audio file (wav, mp3, ogg, flac...). It loads at most **120 seconds**, trims silence, normalises, cuts the clip into **3-second windows** (the model was trained on short clips), scores each window, calibrates, and averages. The answer: `emotion`, `confidence` (kept in the data, not shown), `mood`, `durationSec`, `probabilities`, a `timeline` (the emotion of each 3-second window) and an `explanation`. Silent clips or clips under half a second are refused (400). The model runs on the GPU when there is one. Start: `python -m uvicorn serve:app --app-dir models/src --port 8001` from the repository root.

### Explanation: which parts of the recording the model leaned on (`explain.py`)
An **occlusion map**: the service silences one short block of the recording at a time (0.25 s; longer for long calls, at most 48 blocks), scores the clip again with the same calibrated model, and reports for each block how much the probability of the answer **fell** (`drop`; negative = the block argued against the answer; `rel` = the same scaled to -1..1) and the three most influential moments. A block that straddles two windows re-scores both. It shows **where the model looked, not a proof of why**. If the explanation fails the answer is still returned (`explanation: null`). A long clip is explained in well under a second per 30 s on the GPU.

## In the web app
* **Call review** (`/call-review`, role `nour` or `admin`): upload an audio file (wav, mp3, ogg, flac; up to 15 MB; the first 2 minutes are scored), press **Analyze emotion**. The page shows the **emotion** (for example "Anger"), the **mood** out of 100 and the length of speech, **Through the call** (the emotion of each 3-second window) and **Why this answer**: a strip of blocks, darker = the model leaned on it more, hatched = that part argued against the answer, the three most influential moments in words, and a short note on how it was found and its limits. The page sends the audio to the web app (`POST /call-review/analyze`, CSRF token required), which forwards it to the emotion service (60 s timeout); if the service is not running, the page says so (503).
* **Live call (advisor's voice notes)**: the web app sends each voice note to `POST /emotion/analyze` along with the transcription (20 s limit, the answer is `null` when the service is down). Anger or disgust with a mood of 30 or lower makes the customer hear a raised voice. Checked on real acted clips from CREMA-D through the whole stack: an angry clip gave anger, mood 11 (she answered "I would like you to speak to me politely, please."); a neutral one gave neutral, mood 51 (no reaction); a loud *happy* clip gave anger, mood 34, which is exactly the confusion of acted speech the threshold of 30 is there to limit.
* **Quality analyst**: for a recorded call, each customer sentence is sent to the service; the result becomes the sentence's `mood` and `emotion`, which feed the mood curve, the sentiment criterion and the empathy rule ([04-quality-analyst.md](04-quality-analyst.md)). Without the service the mood falls back to a word list and the review says so.

## Explainability and honesty
The strip is the model's explanation; the page also states the training data (acted speech), the weak class (sad) and that real calls may be harder. The model card (`models/emotion_wavlm_ft_full_aug2.json`) records the data, the recipe, the metrics, the limits and the date (2026-10-10).

## Tests
`models/tests/test_explain.py` (4, no weights needed): silencing the only loud part costs the most; a block that argues against the answer gets a negative drop; a block straddling two windows re-scores both; long calls get longer blocks. Web: `call-review.spec.ts` (the page, the upload route, CSRF, 503). Browser: the whole flow with the real service. The model's accuracy and robustness are measured by `finetune.py` and `eval_robustness.py` (reports in `models/reports/`), not by unit tests.

## Honest limits
**Acted speech only** (CREMA-D, RAVDESS); English; 16 test actors, so clean-accuracy gaps of 2 to 3 points are within noise; codecs are real but noise and rooms are simulated; the mood is a lookup of six numbers, not a measured quantity; 3-second windows ignore longer context; one speaker is assumed (no separation); calibrated on clean speech only. A rise to real use needs real, labelled call audio ([DATA_COLLECTION.md](../../DATA_COLLECTION.md)).

## Files
`models/src/finetune.py` (data, model, training), `degrade.py` (codecs and noise), `eval_robustness.py`, `calibrate.py`, `serve.py`, `explain.py`; `models/registry/` (weights, git-ignored), `models/reports/`, `models/*.json` (cards, calibration); `models/tests/test_explain.py`; web: `app/src/pages/call-review.controller.ts`, `app/views/call-review.njk`, `app/client/app.ts`; `services/agents/quality_analyst/audio.py`.
