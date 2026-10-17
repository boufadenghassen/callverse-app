"""orqestra agents service (FastAPI). Run from services/agents:  ../../../venv/Scripts/python.exe -m uvicorn main:app --port 8000

Real today: the customer simulator and the customer advisor. The web app keeps using demo data for the other agents
(see HttpAgentGateway). The contract is the table in app/README.md.
"""
import re
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import advisor
import customer

app = FastAPI(title="orqestra agents")

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


@app.get("/health")
def health():
    return {"status": "UP", "agents": ["customer", "advisor"]}


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
