"""Schémas d'entrée/sortie : le contrat avec les autres agents."""
from typing import Literal
from pydantic import BaseModel, Field

Language = Literal["fr", "en", "derja"]
Gender = Literal["F", "M"]
Action = Literal["continue", "escalate", "hangup", "resolved"]


class PersonaTemplate(BaseModel):
    id: str
    language: Language
    gender: Gender
    label: str
    names: list[str]
    age_range: tuple[int, int]
    segments: list[str]
    speaking_style: str
    base_emotion: dict[str, float]
    typical_intents: list[str]
    examples: list[str]  # few-shot, crucial pour le derja


class Profile(BaseModel):
    persona_id: str
    name: str
    age: int
    gender: Gender
    language: Language
    segment: str
    seniority_years: int
    history: list[str]
    intents: list[str]                # ordre = ordre d'apparition
    hidden_intent: str | None = None  # ce que le client n'avoue pas d'emblée
    speaking_style: str
    examples: list[str]
    details: dict[str, str] = Field(default_factory=dict)  # infos à donner si on les demande


class EmotionState(BaseModel):
    patience: float = Field(0.7, ge=0, le=1)
    frustration: float = Field(0.1, ge=0, le=1)
    trust: float = Field(0.5, ge=0, le=1)
    urgency: float = Field(0.3, ge=0, le=1)

    def clamp(self) -> "EmotionState":
        for f in ("patience", "frustration", "trust", "urgency"):
            setattr(self, f, max(0.0, min(1.0, getattr(self, f))))
        return self


class Scenario(BaseModel):
    """Entrée : fournie par le Scenario Generation Agent (agent 2)."""
    problem_type: str | None = None   # clé de intents.json
    difficulty: int = Field(3, ge=1, le=5)
    persona_id: str | None = None     # ex: "derja_m"
    language: Language | None = None
    gender: Gender | None = None
    max_turns: int = 12
    seed: int | None = None


class AdvisorSignals(BaseModel):
    """Évaluation de la dernière réponse de l'Advisor, qui pilote l'émotion."""
    relevance: float = 0.5
    empathy: float = 0.5
    repeated_question: bool = False
    wait_seconds: float = 0.0
    resolved: bool = False


class CustomerMessage(BaseModel):
    """Sortie : lue par l'Advisor (texte) et par le Quality Analyst (metadata)."""
    text: str
    emotion: EmotionState
    action: Action = "continue"
    turn: int = 0
    metadata: dict = Field(default_factory=dict)
