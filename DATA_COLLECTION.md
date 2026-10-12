# Collecting real call data for the emotion model

Why: every number so far is acted studio speech with simulated damage. A few hundred real or role-played phone
calls, labelled by people, is the only way to measure how the model behaves on what orqestra will actually hear, and the
best material for the next training round. Aim for **150 to 300 clips from at least 15 different speakers**.

## 1. Rules first (consent and privacy)

* Only record **team members and volunteers** who agree in writing (a short consent line in the sheet below is enough).
  Never use real customer calls without a legal basis, consent and your institution's approval (Tunisian data-protection
  law; GDPR for EU data).
* Role-play must not contain anyone's real personal data: invent names, account numbers and addresses.
* Recordings stay local in `datasets/OWN-CALLS/` (git-ignored). Share them only through your team drive, and delete them on request.

## 2. How to record

| Item | Do this |
|---|---|
| Who | Pairs: one **customer**, one **advisor**. Swap pairs between sessions so each person plays both. |
| Scenarios | Give the customer a **situation card**, not an emotion to act. "You were charged twice and this is the third time you call" produces real irritation; "act angry" produces a caricature. Use the cards in the table below. |
| Emotions to cover | anger, disgust, fear/anxiety, happiness/relief, sadness, neutral. At least 25 clips per emotion. |
| Length | One clip = one customer turn of 2 to 10 seconds, cut from the call. |
| Channel | Record the real channel: normal phone call, mobile network, or a softphone (Zoom, Teams, WhatsApp). Record **the customer's side as received** by the advisor (speakerphone on a second device, or the app's own recording). |
| Variety | At least 3 devices, 2 networks (mobile and Wi-Fi), a quiet room and a noisy one (street, cafe, TV on, fan). Write the condition in the sheet. |
| Format | Save the original (wav or m4a), never re-encode before cutting. File name: `<speaker>_<call>_<turn>.wav`. |
| Language | Record in the languages your users speak (Tunisian Arabic and French, plus English). The model will need them. |

Situation cards (examples; write 15 to 20 more):

| Emotion | Card for the customer |
|---|---|
| Anger | Charged twice, third call this month, nobody solved it. |
| Disgust | You were told the fee is "normal" and found it insulting; the advisor's tone is dismissive. |
| Fear | Your line was cut abroad and you are worried about an unexpected bill. |
| Happiness | The refund you waited for has just arrived and the advisor was very kind. |
| Sadness | You are cancelling after six years, and you really did not want to. |
| Neutral | You ask about your data allowance in a calm, businesslike way. |

## 3. How to label

Each clip is labelled **independently by 3 people** who did not play in that call, listening only to the audio (the model
hears no text context either).

1. Choose one of: `anger`, `disgust`, `fear`, `happy`, `neutral`, `sad`, or `unclear` (use it rather than guessing).
2. Optional but valuable: **arousal** (1 calm to 5 very excited) and **valence** (1 very negative to 5 very positive). They
   let us predict the 0 to 100 mood directly later.
3. Write the **intended** emotion from the situation card in a separate column, so we can see where acting and perception differ.

Quality checks before any training:

* **Agreement:** compute Cohen's kappa between raters; accept the batch if it is **0.6 or higher**, otherwise discuss the
  disagreements and refine the labels guide.
* **Final label:** the majority of 3 raters. Clips with no majority or marked `unclear` by 2 raters are dropped from training but kept for analysis.
* **Splits by speaker:** about 70% of speakers for training, 15% validation, **15% test and never trained on**. Never put
  one person in two splits.

Sheet columns (`datasets/OWN-CALLS/labels.csv`):
`file, speaker, partner, scenario_card, intended_emotion, language, device, network, noise_condition, consent_ok, rater1, rater2, rater3, arousal_mean, valence_mean, final_label, split`

## 4. What to do with it

1. Put the clips and the sheet in `datasets/OWN-CALLS/` and tell me: I will add them to `models/src/finetune.py` as a third dataset and a separate **real-call test set**.
2. First, **score the current model on them without retraining.** That is the honest measure of the gap and tells us how much real data we need.
3. Then fine-tune with them, still holding out the test speakers.

## 5. Public data you can use now

Licences and access conditions change: **read each page before downloading, and keep the attribution files.** Everything here
was checked against the linked page; where I could not confirm the terms it says so.

### Natural or conversational emotional speech (closest to real calls)

| Dataset | What it is | Access | Link |
|---|---|---|---|
| MSP-Podcast | Hundreds of hours of natural podcast speech with emotion categories plus valence, arousal and dominance, at least 5 raters per clip | Free academic licence, but your **institution must sign** the agreement | [UT Dallas MSP lab](https://ecs.utdallas.edu/research/researchlabs/msp-lab/MSP-Podcast.html) |
| IEMOCAP | About 12 hours of dyadic conversations (scripted and improvised) | Electronic release form to USC SAIL, read the licence first | [USC SAIL](https://sail.usc.edu/iemocap/iemocap_release.htm) |
| MELD | About 13,000 utterances from the TV series Friends, with emotion labels | Sources disagree on the licence; **check the official MELD page before use** | [paper](https://arxiv.org/abs/1810.02508) |

### Other languages (your users speak Arabic and French)

| Dataset | What it is | Access | Link |
|---|---|---|---|
| CaFE | Canadian French emotional speech: 12 actors, 6 emotions plus neutral | Free, CC BY-NC-SA 4.0 (non-commercial) | [Zenodo](https://zenodo.org/record/1478765) (use the newest version) |
| KSUEmotions | About 5 hours of Modern Standard Arabic emotional speech, 23 speakers | Through LDC, user agreement (not a free download) | [LDC2017S12](https://catalog.ldc.upenn.edu/LDC2017S12) |
| EYASE | Egyptian Arabic, semi-natural, from TV series; 4 emotions | No official download page found; look in the authors' paper for a data statement | [paper](https://nu.edu.eg/publications/emotion-recognition-system-arabic-speech-case-study-egyptian-accent) |
| SERTUS | Spontaneous **Tunisian dialect** speech with emotion annotation (2025) | Look for the download link on the paper page; none found in search | [paper](https://scitepress.org/PublishedPapers/2025/131340) |
| TuniSER | First Tunisian speech emotion dataset (2022) | Location not found; check the ICNLSP 2022 paper and its authors | [ACL Anthology](https://preview.aclanthology.org/fix_video/2022.icnlsp-1.27.pdf) |

For Tunisian data, **contact the authors directly**: researchers usually share corpora for academic work, and local data matters most for your users.

### More acted English emotion (more actors, narrows the test uncertainty)

| Dataset | What it is | Access | Link |
|---|---|---|---|
| EmoV-DB | 4 speakers, several emotional styles | OpenSLR; **read the licence link on the page** | [OpenSLR 115](https://openslr.org/115/) |
| SAVEE, TESS, EMO-DB | Small classic acted corpora (4 men; 2 women; 10 actors) | Terms not confirmed here: use the official pages of the universities that publish them | search the dataset name |

### Real noise and rooms (replaces my simulated noise and reverb in augmentation)

| Dataset | What it is | Access | Link |
|---|---|---|---|
| MUSAN | About 109 hours of music, speech and noise, 16 kHz | Creative Commons or public domain per file; keep the per-file LICENSE files | [paper](https://arxiv.org/abs/1510.08484), [OpenSLR 17](https://openslr.org/17/) |
| RIRS_NOISES | Real and simulated **room impulse responses** plus point-source noises, 1.3 GB | Apache 2.0 | [OpenSLR 28](https://openslr.org/28/) |
| DEMAND | Multi-channel noise recorded in diverse real places (cafe, street, kitchen, office) | CC BY-SA 3.0 on Zenodo (mirrors say CC BY 4.0: rely on Zenodo) | [Zenodo](https://zenodo.org/records/1227121) |

Order of value: **your own recorded calls first**, then Tunisian/Arabic/French data, then MSP-Podcast or IEMOCAP for natural
speech, then real noise and room recordings.

## 6. What I need back

* A first batch of **30 clips from 5 speakers** with the labels sheet, so I can run the current model on it and tell you the real error rate.
* Which of the licensed datasets your institution can sign for. I will add each one to the pipeline as it arrives.
