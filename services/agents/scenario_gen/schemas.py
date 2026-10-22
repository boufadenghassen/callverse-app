"""Schemas of the Scenario Generation Agent (Training Lead).

`SimScenario` is the contract with the Customer Sim: it is field for field the `Scenario` model of the
Customer Sim agent (see tests/fixtures/customer_sim_schemas.py). Everything else in this file is ours.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

Language = Literal["fr", "en", "derja"]
Gender = Literal["F", "M"]
Segment = Literal["new", "loyal", "dissatisfied", "premium", "at_risk"]
Emotion = Literal["anger", "disgust", "fear", "happy", "neutral", "sad"]
Mode = Literal["standard", "multi_event", "rare_event"]
Kind = Literal["generated", "ramp", "replay", "mutation", "adaptive"]


# --------------------------------------------------------------------------- contract with the Customer Sim
class SimScenario(BaseModel):
    """What the Customer Sim reads. Do not rename or retype these fields without telling its owner."""

    problem_type: str | None = None  # key of the Customer Sim's intents.json
    difficulty: int = Field(3, ge=1, le=5)
    persona_id: str | None = None  # "<language>_<f|m>", for example "derja_m"
    language: Language | None = None
    gender: Gender | None = None
    max_turns: int = 12
    seed: int | None = None


# --------------------------------------------------------------------------- our own scenario model
class ScenarioSpec(BaseModel):
    """The canonical definition of a scenario. Everything else is derived from it, so replaying or
    mutating a scenario means copying and editing a spec."""

    intent: str
    difficulty: int = Field(3, ge=1, le=5)
    language: Language
    gender: Gender
    segment: Segment
    events: list[str] = Field(default_factory=list)
    extra_intents: list[str] = Field(default_factory=list)  # filled when "second_problem" is an event
    hidden_intent: str | None = None  # filled when "hidden_intent" is an event
    max_turns: int = Field(12, ge=2, le=40)
    seed: int = Field(ge=0)


class TrainingScenario(BaseModel):
    id: str
    kind: Kind = "generated"
    parent_id: str | None = None
    mutation_log: list[str] = Field(default_factory=list)

    title: str
    category: str
    opening_emotion: Emotion
    skills: list[str]  # skills this scenario trains
    success_criteria: list[str]
    complications: list[str]  # English text of each event, for trainers and for Customer Sim prompts
    customer_card: str  # situation card in the scenario language (what the customer lives)
    trainer_brief: str  # English summary for the trainer or the advisor
    tags: list[str] = Field(default_factory=list)

    spec: ScenarioSpec
    sim: SimScenario  # send exactly this to the Customer Sim
    sim_extensions: dict[str, Any] = Field(default_factory=dict)  # proposed extra fields, ignored today

    enrichment: Literal["template", "llm"] = "template"
    notes: list[str] = Field(default_factory=list)


class WebScenario(BaseModel):
    """The flat scenario-card contract consumed by the web application."""

    id: str
    title: str
    profile: str
    difficulty: str
    origin: str


# --------------------------------------------------------------------------- requests
class GenerateRequest(BaseModel):
    """Everything is optional: an empty body gives a fully random scenario."""

    intent: str | None = None
    difficulty: int | None = Field(None, ge=1, le=5)
    language: Language | None = None
    gender: Gender | None = None
    segment: Segment | None = None
    mode: Mode = "standard"
    events: list[str] = Field(default_factory=list)  # events that must be present
    focus_skill: str | None = None  # favour intents and events that train this skill
    advisor_id: str | None = None  # owner used by the Coach to scope training history
    max_turns: int | None = Field(None, ge=2, le=40)
    seed: int | None = Field(None, ge=0)
    enrich: bool = False  # ask the LLM to rewrite the texts (falls back to templates)


class BatchRequest(BaseModel):
    count: int = Field(10, ge=1, le=100)
    difficulty_min: int = Field(1, ge=1, le=5)
    difficulty_max: int = Field(5, ge=1, le=5)
    languages: list[Language] | None = None
    mode: Mode = "standard"
    seed: int | None = Field(None, ge=0)
    enrich: bool = False


class RampRequest(BaseModel):
    """Same situation, harder and harder: events are added level after level."""

    intent: str | None = None
    language: Language | None = None
    gender: Gender | None = None
    start: int = Field(1, ge=1, le=5)
    end: int = Field(5, ge=1, le=5)
    seed: int | None = Field(None, ge=0)


MutationName = Literal[
    "harder",
    "easier",
    "set_difficulty",
    "set_language",
    "set_gender",
    "set_intent",
    "set_segment",
    "set_max_turns",
    "add_event",
    "remove_event",
    "add_second_problem",
    "set_hidden_intent",
    "reseed",
]


class MutationOp(BaseModel):
    op: MutationName
    value: Any = None


class MutateRequest(BaseModel):
    ops: list[MutationOp] = Field(default_factory=list)
    random: bool = False  # apply one or two random what-if changes
    seed: int | None = Field(None, ge=0)
    enrich: bool = False


class ReplayRequest(BaseModel):
    reseed: bool = False  # False: identical scenario and seed. True: same situation, new randomness.


class QAWeakness(BaseModel):
    """One score from the Quality Analyst. The scale is 0 to 1 or 0 to 100 (values above 1 are percentages)."""

    criterion: str
    score: float = Field(ge=0, le=100)
    advisor_id: str | None = None


class TrainingPlanRequest(BaseModel):
    advisor_id: str
    weaknesses: list[QAWeakness] = Field(min_length=1)
    size: int = Field(6, ge=1, le=30)  # number of scenarios in the plan
    current_level: int = Field(2, ge=1, le=5)  # difficulty at which the advisor is comfortable today
    threshold: float = Field(0.7, gt=0, le=1)  # scores under this are weaknesses
    max_skills: int = Field(3, ge=1, le=7)
    languages: list[Language] | None = None
    seed: int | None = Field(None, ge=0)


class FocusItem(BaseModel):
    skill: str
    gap: float  # 0 to 1, larger = weaker
    criteria: list[str]  # the QA criteria that pointed to this skill


class TrainingPlan(BaseModel):
    advisor_id: str
    needs_training: bool
    focus: list[FocusItem]
    scenarios: list[TrainingScenario]
    rationale: list[str]


class ProgressRequest(BaseModel):
    before: list[QAWeakness]
    after: list[QAWeakness]


class ProgressItem(BaseModel):
    criterion: str
    before: float
    after: float
    delta: float
    status: Literal["improved", "regressed", "unchanged"]


class ProgressReport(BaseModel):
    items: list[ProgressItem]
    improved: int
    regressed: int
    unchanged: int
