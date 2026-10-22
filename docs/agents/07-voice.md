# 7. Voice: speech out and speech in (shared)

Agents have been given a voice and an ear. Two components of the agents service, used by the customer simulator, the advisor console, the workforce and quality pages and the quality analyst's recording review.

## Text to speech: neural voices (`services/agents/voice.py`)
* **Engine**: [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) v1.0 (Apache 2.0), running **offline on the CPU** through onnxruntime (`CPUExecutionProvider`, 4 threads by default: measured fastest on a 12-thread laptop; `VOICE_THREADS` changes it). Model files (not in git): `models/voices/kokoro-v1.0.onnx` (325 MB) and `voices-v1.0.bin` (28 MB), downloaded once.
* **Voices**: the advisor speaks with `am_michael`; each customer persona has its own voice: impatient `af_nova`, anxious `af_sky`, angry premium `af_bella`, loyal at risk `af_heart`, new subscriber `af_nicole` (also the default).
* **Mood shapes the speed, not the emotion**: Kokoro cannot act emotions, so an upset customer speaks **faster** and a content one **slower**: speed = 1 + (50 - mood) / 250, limited to 0.85 (mood 100) to 1.2 (mood 0). The advisor always speaks at normal speed.
* **Output**: a 16-bit mono WAV. A cache of the last **64** sentences avoids re-synthesising; one synthesis runs at a time to keep latency predictable.
* **Warm-up**: the model loads in a background thread at service start, so the first spoken line does not wait about 40 seconds.
* `POST /voice/speak` (agents): `text` 1 to 400 characters, `role` advisor or customer, optional `persona`, `mood` 0 to 100; answers `audio/wav`, or **503** if the model files are missing (the web app then falls back to the browser's own voice).

## Speech to text (`services/agents/stt.py`)
* **Engine**: OpenAI **Whisper `base.en`** (English, 290 MB) through the Hugging Face pipeline; **offline**, on the GPU when there is one (half precision) else the CPU. The model comes from the normal Hugging Face cache (`STT_MODEL` changes it).
* **Voice notes**: `POST /voice/transcribe` takes a 16 kHz mono WAV (the web page converts the microphone recording itself, so no ffmpeg is needed), up to about 2 minutes and 5 MB; the first 60 seconds are used; a silent or too short recording is refused with a kind message ("I could not hear anything. Try again, closer to the microphone."). Answers `{text, seconds}`; **503** if the model is missing.
* **Recordings with times** (used by the quality analyst): `transcribe_segments` finds where somebody speaks in one channel with an **energy-based voice detector** (frames louder than 12 % of the channel's own 95th-percentile level, joined across pauses shorter than 0.6 s, stretches shorter than 0.4 s dropped), then transcribes each stretch (with a 0.15 s margin) in a batch and returns `[{text, start, end}]`. Cutting at silences gives exact times, which Whisper's own timestamps did not.

## In the web app
* **Listen** buttons (`data-speak`) on the advisor's suggested answer, the quality analyst's coaching hint and tips and the workforce recommendations. They call the web app's `POST /voice/speak` (any signed-in user; CSRF token required; text up to 400 characters; the page caches answers for an hour).
* **Live call** (advisor console): the customer's replies are **spoken, sentence by sentence**, in her persona's voice shaped by her mood ("Speak her replies" checkbox); the advisor's **typed replies are said aloud** in the advisor voice before the customer answers ("Say my typed replies aloud"); a **voice note** button records the advisor, the page converts it to 16 kHz WAV, `POST /voice/transcribe` writes it down, the note stays playable in the call log and is sent as the reply.
* **Fallback**: if there is no neural voice (or the agents are down) the page uses the browser's built-in speech synthesis; if there is no speech model, voice notes say so and typing still works.
* **Security details**: the content security policy allows audio from `blob:` URLs (`media-src 'self' blob:`) and the microphone only for the app's own origin (`Permissions-Policy: microphone=(self)`).

## Tests
`services/agents/tests/test_agents.py`: voice speed follows mood and voices follow persona; the voice endpoint returns audio or says it is missing; voice notes are written down or refused (these skip when the models are not installed, as in CI). Web: `voice.spec.ts` (6) covers the routes, validation, CSRF, the 503 fallbacks and the gateway. Browser: Listen buttons, spoken replies, typed replies said aloud, a voice note end to end, and "voice notes fail kindly".

## Honest limits
English only (Whisper `base.en`, Kokoro `en-us`); no emotion in the voice (speed only); 400 characters per sentence; Whisper `base` makes mistakes on accents and noise; the energy-based voice detector assumes clean, separate channels; the first call after a restart waits for the models (they warm up in the background).

## Files
`services/agents/voice.py`, `stt.py`, `main.py` (voice routes), `app/src/pages/voice.controller.ts`, `app/client/app.ts` (speak, record, convert to WAV, fallback), `app/src/setup.ts` (CSP and Permissions-Policy), `app/test/voice.spec.ts`.
