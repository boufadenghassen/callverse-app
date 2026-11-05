"""The template library: intents, events (complications), skills and the QA criteria mapping."""
import json
import logging
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("scenario_gen.catalog")

DATA_FILE = Path(__file__).parent / "data" / "catalog.json"

# Names the Quality Analyst might use (French or English) -> canonical criterion keys of catalog.json.
CRITERION_ALIASES = {
    "conformite": "compliance",
    "conformity": "compliance",
    "pertinence": "relevance",
    "exactitude": "accuracy",
    "respect_des_procedures": "procedure",
    "respect_procedures": "procedure",
    "procedures": "procedure",
    "procedure_compliance": "procedure",
    "satisfaction_client": "satisfaction",
    "customer_satisfaction": "satisfaction",
    "sentiments": "sentiment",
    "customer_sentiment": "sentiment",   # the name the Quality Analyst uses
}


class CatalogError(ValueError):
    pass


def normalize_key(text: str) -> str:
    """'Respect des procédures' -> 'respect_des_procedures'."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return "_".join(stripped.lower().replace("-", " ").split())


@dataclass(frozen=True)
class Intent:
    key: str
    category: str
    title: str
    base_difficulty: int
    opening_emotion: str
    skills: tuple[str, ...]
    typical_segments: tuple[str, ...]
    success_criteria: tuple[str, ...]
    card: dict[str, str]


@dataclass(frozen=True)
class Event:
    key: str
    rare: bool
    text: str
    expect: str
    stresses: tuple[str, ...]


class Catalog:
    def __init__(self, raw: dict[str, Any]):
        self.languages: list[str] = list(raw["languages"])
        self.segments: list[str] = list(raw["segments"])
        self.skills: dict[str, str] = dict(raw["skills"])
        self.criteria: dict[str, list[tuple[str, float]]] = {
            k: [(s, float(w)) for s, w in v] for k, v in raw["criteria"].items()
        }
        self.intents: dict[str, Intent] = {}
        for item in raw["intents"]:
            intent = Intent(
                key=item["key"],
                category=item["category"],
                title=item["title"],
                base_difficulty=int(item["base_difficulty"]),
                opening_emotion=item["opening_emotion"],
                skills=tuple(item["skills"]),
                typical_segments=tuple(item["typical_segments"]),
                success_criteria=tuple(item["success_criteria"]),
                card=dict(item["card"]),
            )
            self.intents[intent.key] = intent
        self.events: dict[str, Event] = {}
        for item in raw["events"]:
            event = Event(
                key=item["key"],
                rare=bool(item["rare"]),
                text=item["text"],
                expect=item["expect"],
                stresses=tuple(item["stresses"]),
            )
            self.events[event.key] = event
        self._validate()

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, path: Path = DATA_FILE) -> "Catalog":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def _validate(self) -> None:
        for intent in self.intents.values():
            missing_langs = [lang for lang in self.languages if not intent.card.get(lang)]
            if missing_langs:
                raise CatalogError(f"intent {intent.key} has no card for {missing_langs}")
            if intent.opening_emotion not in {"anger", "disgust", "fear", "happy", "neutral", "sad"}:
                raise CatalogError(f"intent {intent.key} has an unknown emotion {intent.opening_emotion}")
            for skill in intent.skills:
                if skill not in self.skills:
                    raise CatalogError(f"intent {intent.key} uses unknown skill {skill}")
            for segment in intent.typical_segments:
                if segment not in self.segments:
                    raise CatalogError(f"intent {intent.key} uses unknown segment {segment}")
        for event in self.events.values():
            for skill in event.stresses:
                if skill not in self.skills:
                    raise CatalogError(f"event {event.key} stresses unknown skill {skill}")
        for criterion, pairs in self.criteria.items():
            for skill, _ in pairs:
                if skill not in self.skills:
                    raise CatalogError(f"criterion {criterion} maps to unknown skill {skill}")

    # ------------------------------------------------------------------ alignment with the Customer Sim
    def restrict_intents(self, keys: set[str]) -> None:
        """Keep only the intents the Customer Sim knows, so problem_type always resolves on its side."""
        kept = {k: v for k, v in self.intents.items() if k in keys}
        if not kept:
            log.error("none of our intent keys exist in the Customer Sim's intents; keeping all of ours")
            return
        dropped = sorted(set(self.intents) - set(kept))
        if dropped:
            log.warning("intents unknown to the Customer Sim, not generated: %s", dropped)
        self.intents = kept

    # ------------------------------------------------------------------ helpers
    def intent(self, key: str) -> Intent:
        try:
            return self.intents[key]
        except KeyError:
            raise CatalogError(f"unknown intent '{key}'. Known: {sorted(self.intents)}") from None

    def event(self, key: str) -> Event:
        try:
            return self.events[key]
        except KeyError:
            raise CatalogError(f"unknown event '{key}'. Known: {sorted(self.events)}") from None

    def check_skill(self, skill: str) -> str:
        if skill not in self.skills:
            raise CatalogError(f"unknown skill '{skill}'. Known: {sorted(self.skills)}")
        return skill

    def criterion_to_skills(self, criterion: str) -> list[tuple[str, float]] | None:
        """Map a QA criterion (or a skill name used directly) to [(skill, weight)]. None if unknown."""
        key = normalize_key(criterion)
        if key in self.skills:
            return [(key, 1.0)]
        key = CRITERION_ALIASES.get(key, key)
        return self.criteria.get(key)


def intent_keys_from_file(path: str | Path) -> set[str]:
    """Read the keys of the Customer Sim's intents.json (a dict keyed by intent, or a list of objects)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        inner = data.get("intents")
        if isinstance(inner, (dict, list)):
            data = inner
    if isinstance(data, dict):
        return {str(k) for k in data}
    if isinstance(data, list):
        keys: set[str] = set()
        for item in data:
            if isinstance(item, str):
                keys.add(item)
            elif isinstance(item, dict):
                for field in ("key", "id", "name", "problem_type"):
                    if isinstance(item.get(field), str):
                        keys.add(item[field])
                        break
        return keys
    raise CatalogError("intents file must be a JSON object or list")


def compare_with_sim_intents(catalog: Catalog, path: str | Path) -> dict[str, list[str]]:
    """Report which of our intent keys the Customer Sim does not know, and which of its keys we do not cover."""
    theirs = intent_keys_from_file(path)
    ours = set(catalog.intents)
    return {
        "ours_unknown_to_sim": sorted(ours - theirs),
        "sim_not_covered_by_us": sorted(theirs - ours),
        "shared": sorted(ours & theirs),
    }
