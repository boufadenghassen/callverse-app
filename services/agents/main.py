"""orqestra agents service (FastAPI). Run from services/agents:  ../../../venv/Scripts/python.exe -m uvicorn main:app --port 8000

Real today: the customer simulator, the customer advisor, the neural voice, speech to text and the workforce agent (Erlang C). The web app keeps using demo data for the other agents
(see HttpAgentGateway). The contract is the table in app/README.md.
"""
import re
import threading
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import advisor
import customer
from quality_analyst import audio as quality_audio
from quality_analyst import engine as quality
from quality_analyst import evaluation as quality_eval
from quality_analyst import semantic as quality_semantic
from quality_analyst import store as quality_store
import stt
import voice
import routing
import scheduling
import workforce


@asynccontextmanager
async def lifespan(_app):
    # load the voice model in the background, so the first spoken line does not wait for it
    quality_store.ensure_history()
    if quality.SEMANTIC:   # the first review otherwise waits ~15 s for the embedding model, and the accuracy page for its report
        threading.Thread(target=lambda: (quality_semantic.scores('Ready.'), quality_eval.report()), daemon=True).start()
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
    return {"status": "UP", "agents": ["customer", "advisor", "workforce", "quality"], "voice": voice.available(), "listen": stt.available()}


@app.post("/voice/speak")
def speak(body: SpeakIn):
    """The text as a WAV, in the advisor's voice or the customer's (a voice per persona, faster when she is upset)."""
    if not voice.available():
        raise HTTPException(503, "The neural voice is not installed (see services/agents/README.md).")
    return Response(voice.speak(body.text, body.role, body.persona, body.mood), media_type="audio/wav")


@app.post("/advisor/suggest")
def suggest(body: SuggestIn):
    return advisor.suggest(body.query)


@app.get("/advisor/customers/{customer_id}")
def advisor_customer(customer_id: str = Path(pattern=r"^[A-Z]{2}-\d{4}$")):
    """The customer's 360-degree context (name, contract, open tickets, mood...) for the advisor's sidebar."""
    customer_record = advisor.get_customer(customer_id)
    if customer_record is None:
        raise HTTPException(404, f"No customer with id {customer_id}.")
    return customer_record


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


@app.get("/workforce/routing")
def workforce_routing():
    """Who should work which queue for the rest of the day: ranked moves per hour, checked by a simulation."""
    return routing.plan()


@app.get("/workforce/schedule")
def workforce_schedule():
    """Lunch plan for a typical day (naive: everybody at noon, against a planned spread) and the overtime still needed."""
    return scheduling.plan()


# ---- quality analyst ---------------------------------------------------------------------------------
class TurnIn(BaseModel):
    speaker: Literal["advisor", "customer"]
    text: str = Field(min_length=1, max_length=1000)
    start: float | None = Field(None, ge=0, le=7200)
    end: float | None = Field(None, ge=0, le=7200)
    mood: int | None = Field(None, ge=0, le=100)
    emotion: str | None = Field(None, max_length=20)


class ReviewIn(BaseModel):
    advisor: str = Field(min_length=1, max_length=60)
    turns: list[TurnIn] = Field(min_length=1, max_length=200)


class ReviewCallIn(BaseModel):
    callId: str = Field(pattern=r"^[0-9a-f]{16}$")
    advisor: str = Field(min_length=1, max_length=60)


def _store(turns: list[dict], advisor_name: str, source: str, outcome: dict | None = None) -> dict:
    result = quality.review(turns, advisor_name, quality_store.next_call_id(), source=source, outcome=outcome)
    return quality_store.save(result)


@app.post("/quality/review")
def quality_review(body: ReviewIn):
    """Score a transcript (turns with speaker and text; times and mood are optional) and keep it."""
    return _store([t.model_dump() for t in body.turns], body.advisor.strip(), "api")


@app.post("/quality/review-call")
def quality_review_call(body: ReviewCallIn):
    """Score a live call of the advisor console (a customer simulator session) and keep it."""
    try:
        turns, outcome, _persona = customer.transcript(body.callId)
    except KeyError:
        raise HTTPException(404, "Unknown call.")
    if not any(t["speaker"] == "advisor" for t in turns):
        raise HTTPException(400, "Say something to the customer first: there is nothing to review yet.")
    return _store(turns, body.advisor.strip(), "live call", outcome)


@app.post("/quality/review-audio")
async def quality_review_audio(req: Request, advisor_name: str = Query("Unknown advisor", alias="advisor", min_length=1, max_length=60)):
    """Score a two-channel recording (advisor left, customer right, up to 10 MB)."""
    if not quality_audio.available():
        raise HTTPException(503, "The speech-to-text model is not installed (see services/agents/README.md).")
    body = await req.body()
    if not body or len(body) > 10_000_000:
        raise HTTPException(400, "Send a recording of up to 10 MB.")
    try:
        turns = await run_in_threadpool(quality_audio.transcript, body)
    except quality_audio.NeedsTwoChannels as e:
        raise HTTPException(422, str(e))
    except stt.BadAudio as e:
        raise HTTPException(400, str(e))
    return _store(turns, advisor_name.strip(), "recording")


@app.get("/quality/reviews")
def quality_reviews(limit: int = Query(20, ge=1, le=100), advisor_name: str | None = Query(None, alias="advisor", max_length=60),
                    rule: str | None = Query(None, pattern=r"^[a-z_]{3,30}$"), below: int | None = Query(None, ge=1, le=101)):
    """Latest reviews. Filters: `advisor`, `rule` (calls where it fired and was not disputed), `below` (overall score under this number)."""
    return quality_store.recent(limit, advisor_name, rule, below)


@app.get("/quality/reviews/{call_id}")
def quality_one(call_id: str = Path(pattern=r"^CALL-\d{4,6}$")):
    found = quality_store.get(call_id)
    if not found:
        raise HTTPException(404, "Unknown call.")
    return found


@app.get("/quality/analytics")
def quality_analytics():
    """Team and per-advisor analytics over the stored calls: trends, frequent errors, root causes, coaching plans."""
    return quality_store.analytics()


@app.get("/quality/sample-call.wav")
async def quality_sample_call():
    """A two-channel example call (advisor left, customer right) with mistakes on purpose, spoken by the neural voices."""
    if not voice.available():
        raise HTTPException(503, "The neural voice is not installed (see services/agents/README.md).")
    return Response(await run_in_threadpool(quality_audio.sample_call), media_type="audio/wav", headers={"Content-Disposition": 'attachment; filename="sample-call.wav"'})


@app.get("/quality/evaluation")
def quality_evaluation():
    """How accurate the analyst is: precision and recall per rule on hand-labelled calls, development and held-out test."""
    return quality_eval.report()


class FeedbackIn(BaseModel):
    callId: str = Field(pattern=r"^CALL-\d{4,6}$")
    rule: str = Field(max_length=40)
    turn: int = Field(ge=0, le=1000)
    verdict: Literal["agree", "disagree", "clear"]
    by: str = Field("reviewer", min_length=1, max_length=40)


@app.post("/quality/feedback")
def quality_feedback(body: FeedbackIn):
    """A human reviewer's verdict on one finding: it is an error (agree) or not (disagree). Disputed findings stop counting in the score."""
    found = quality_store.get(body.callId)
    if not found or not any(e["rule"] == body.rule and e["turn"] == body.turn for e in found["errors"]):
        raise HTTPException(404, "No such finding.")
    quality_store.set_feedback(body.callId, body.rule, body.turn, body.verdict, body.by)
    return quality_store.get(body.callId)
