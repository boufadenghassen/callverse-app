"""orqestra agents service (FastAPI). Run from services/agents:  ../../../venv/Scripts/python.exe -m uvicorn main:app --port 8000

Real today: the customer simulator, the customer advisor, the neural voice, speech to text and the workforce agent (Erlang C). The web app keeps using demo data for the other agents
(see HttpAgentGateway). The contract is the table in app/README.md.
"""
import re
import threading
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

import advisor
import customer
import stt
import voice
import workforce


@asynccontextmanager
async def lifespan(_app):
    # load the voice model in the background, so the first spoken line does not wait for it
    if voice.available():
        threading.Thread(target=lambda: voice.speak("Ready."), daemon=True).start()
    if stt.available():
        threading.Thread(target=stt._pipeline, daemon=True).start()
    yield


app = FastAPI(title="orqestra agents", lifespan=lifespan)

Persona = Literal["IMPATIENT", "ANXIOUS", "ANGRY_PREMIUM", "LOYAL_AT_RISK", "NEW_SUBSCRIBER"]


class SuggestIn(BaseModel):
    customer_id: str = Field(pattern=r"^[A-Z]{2}-\d{4}$")
    query: str = Field(min_length=3, max_length=500)


class CallIn(BaseModel):
    persona: Persona
    mix: Persona | None = None
    difficulty: Literal["EASY", "MEDIUM", "HARD"] = "MEDIUM"
    intent: Literal["BILLING", "ROAMING", "CANCELLATION"] = "BILLING"
    memory: bool = False


class SayIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    role: Literal["advisor", "customer"] = "advisor"
    persona: Persona | None = None
    mood: int = Field(50, ge=0, le=100)


@app.get("/health")
def health():
    return {"status": "UP", "agents": ["customer", "advisor", "workforce"], "voice": voice.available(), "listen": stt.available()}


@app.post("/voice/speak")
def speak(body: SpeakIn):
    """The text as a WAV, in the advisor's voice or the customer's (a voice per persona, faster when she is upset)."""
    if not voice.available():
        raise HTTPException(503, "The neural voice is not installed (see services/agents/README.md).")
    return Response(voice.speak(body.text, body.role, body.persona, body.mood), media_type="audio/wav")


@app.post("/advisor/suggest")
def suggest(body: SuggestIn):
    return advisor.suggest(body.query)


@app.post("/customer/sessions")
def start_call(body: CallIn):
    return customer.start(body.persona, body.mix, body.difficulty, body.intent, body.memory)


@app.post("/customer/sessions/{sid}/say")
def say(sid: str, body: SayIn):
    if not re.fullmatch(r"[0-9a-f]{16}", sid):
        raise HTTPException(404, "Unknown call.")
    try:
        return customer.say(sid, body.text)
    except KeyError:
        raise HTTPException(404, "Unknown call.")


@app.post("/voice/transcribe")
async def transcribe(req: Request):
    """A voice note (16 kHz mono WAV, up to 5 MB) as text."""
    if not stt.available():
        raise HTTPException(503, "The speech-to-text model is not installed (see services/agents/README.md).")
    body = await req.body()
    if not body or len(body) > 5_000_000:
        raise HTTPException(400, "Send a recording of up to about 2 minutes.")
    try:
        return stt.transcribe(body)
    except stt.BadAudio as e:
        raise HTTPException(400, str(e))


class SimulateIn(BaseModel):
    queue: str = Field(pattern=r"^[A-E]$")
    extraAdvisors: int = Field(ge=-5, le=10)
    from_: str = Field(alias="from", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    to: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


@app.get("/workforce/forecast")
def workforce_forecast(queue: str = Query("B", pattern=r"^[A-E]$")):
    """Calls per hour for the day: the actual so far and the forecast (a point per opening hour)."""
    return workforce.forecast(queue)


@app.post("/workforce/simulate")
def workforce_simulate(body: SimulateIn):
    if body.from_ >= body.to:
        raise HTTPException(422, "The end time must be after the start time.")
    return workforce.simulate(body.queue, body.extraAdvisors, body.from_, body.to)
