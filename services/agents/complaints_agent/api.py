"""HTTP endpoints of the complaint agent, mounted by main.py under /complaints."""
import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from quality_analyst import store as quality_store

from . import engine, store

router = APIRouter(prefix="/complaints", tags=["complaints"])
CASE_ID = re.compile(r"^CMP-\d{1,6}$")
ACTIONS = ("take", "escalate", "severity", "alert", "resolve", "close", "reopen")


class TriageIn(BaseModel):
    text: str = Field(min_length=10, max_length=1500)
    customer_id: str | None = Field(None, pattern=r"^[A-Z]{2}-\d{4}$")


class ComplaintIn(TriageIn):
    channel: Literal["call", "email", "chat", "social", "branch", "app"] = "call"


class ActIn(BaseModel):
    by: str = Field(min_length=1, max_length=40, pattern=r"^[\w .'-]+$")
    note: str = Field("", max_length=300)
    resolution: str | None = Field(None, max_length=20)
    level: Literal["Critical", "High", "Medium", "Low"] | None = None
    trusted: bool | None = None


class FromCallIn(BaseModel):
    call_id: str = Field(pattern=r"^CALL-\d+$")


def _known(customer_id: str | None) -> None:
    if customer_id and engine.advisor.get_customer(customer_id) is None:
        raise HTTPException(404, f"No customer with id {customer_id}.")


def _case_id(case_id: str) -> str:
    if not CASE_ID.match(case_id):
        raise HTTPException(404, "No such case.")
    return case_id


@router.get("/open")
def open_cases():
    """The open cases (waiting or taken), the most dangerous first: severity, escalation risk, deadline and early warning, each with its reasons."""
    return store.analysed(status=("open", "taken"))


@router.get("/insights")
def insights():
    """Root causes and trends over the stored cases, SLA and trust rates, repeat contacts."""
    return store.insights()


@router.get("/follow-ups")
def follow_ups():
    """Resolved cases waiting for the call that checks the customer trusts us again."""
    return store.follow_ups()


def _customer_words(review: dict) -> str:
    return " ".join(t["text"] for t in review["turns"] if t["speaker"] == "customer")[:1000]


@router.get("/from-calls")
def from_calls():
    """Calls the quality analyst scored where the customer hung up, left upset or nothing was agreed, and that are not a complaint yet."""
    have = {c["call_id"] for c in store.all_cases() if c["call_id"]}
    now, out = store.now(), []
    for r in quality_store.recent(limit=200):
        if r["callId"] in have:
            continue
        rules = {e["rule"] for e in r.get("errors", [])}
        mood = next((t["mood"] for t in reversed(r.get("turns", [])) if t["speaker"] == "customer" and t.get("mood") is not None), None)
        why = (["the customer hung up"] if "hang_up" in rules else []) + (["nothing was agreed"] if "unresolved" in rules else []) \
            + ([f"the customer left in a mood of {mood}/100"] if mood is not None and mood <= 25 else [])
        text = _customer_words(r)
        if why and len(text) >= 10:
            out.append(dict(callId=r["callId"], advisor=r["advisor"], overall=r["overall"], why=why, text=text, triage=engine.triage(text, None, now)))
    return out[:8]


@router.post("/from-call")
def from_call(body: FromCallIn):
    """Open a complaint from a scored call: the customer's own words in that call become the case."""
    review = quality_store.get(body.call_id)
    if review is None:
        raise HTTPException(404, f"No call {body.call_id}.")
    if any(c["call_id"] == body.call_id for c in store.all_cases()):
        raise HTTPException(409, "This call is already a complaint.")
    text = _customer_words(review)
    if len(text) < 10:
        raise HTTPException(422, "The customer said too little in this call to open a case.")
    case = store.create(text, None, "call", "quality", call_id=body.call_id, who="quality analyst")
    return store.detail(case["id"])


@router.post("/triage")
def triage(body: TriageIn):
    """Read a complaint without saving it: root cause, severity, escalation risk, deadline and first actions, with the reasons."""
    _known(body.customer_id)
    return engine.triage(body.text, body.customer_id, store.now(), store.all_cases())


@router.post("")
def create(body: ComplaintIn):
    """Open a case from a complaint."""
    _known(body.customer_id)
    case = store.create(body.text, body.customer_id, body.channel)
    return store.detail(case["id"])


@router.get("/{case_id}")
def detail(case_id: str):
    try:
        return store.detail(_case_id(case_id))
    except KeyError:
        raise HTTPException(404, "No such case.")


@router.post("/{case_id}/{action}")
def act(case_id: str, action: str, body: ActIn):
    """take, escalate (one level up), severity (set a level), alert (tell a supervisor), resolve (with how), close (after the follow-up call) or reopen."""
    if action not in ACTIONS:
        raise HTTPException(404, "Unknown action.")
    try:
        store.act(_case_id(case_id), action, body.by, body.note, resolution=body.resolution, level=body.level, trusted=body.trusted)
        return store.detail(case_id)
    except KeyError:
        raise HTTPException(404, "No such case.")
    except ValueError as e:
        raise HTTPException(422, str(e))
