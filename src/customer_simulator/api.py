"""API FastAPI pour les autres agents.  Lancer : uvicorn customer_simulator.api:app"""
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .agent import CustomerSimulatorAgent
from .llm import make_llm
from .schemas import Scenario, CustomerMessage

app = FastAPI(title="CallVerse - Customer Simulator Agent")
SESSIONS: dict[str, CustomerSimulatorAgent] = {}


class StartResponse(BaseModel):
    session_id: str
    message: CustomerMessage


class ReplyRequest(BaseModel):
    advisor_text: str
    wait_seconds: float = 0.0


@app.post("/sessions", response_model=StartResponse)
def start(scenario: Scenario):
    agent = CustomerSimulatorAgent(make_llm("LLM"), make_llm("EVAL"))
    sid = uuid4().hex
    SESSIONS[sid] = agent
    return StartResponse(session_id=sid, message=agent.start(scenario))


@app.post("/sessions/{sid}/reply", response_model=CustomerMessage)
def reply(sid: str, req: ReplyRequest):
    agent = SESSIONS.get(sid)
    if not agent:
        raise HTTPException(404, "session inconnue")
    return agent.reply(req.advisor_text, req.wait_seconds)
