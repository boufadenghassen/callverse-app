"""Scenario builder: turns a request (or nothing at all) into a scenario, deterministically from a seed."""
import hashlib
import random

from .catalog import Catalog, CatalogError
from .schemas import (
    GenerateRequest,
    Kind,
    RampRequest,
    ScenarioSpec,
    SimScenario,
    TrainingScenario,
)

MAX_SEED = 2**31 - 1

DEFAULT_MAX_TURNS = {1: 8, 2: 10, 3: 12, 4: 14, 5: 16}
# how many complications a normal scenario carries at each difficulty level
EVENTS_PER_LEVEL = {1: (0, 0), 2: (0, 1), 3: (1, 1), 4: (1, 2), 5: (2, 3)}
# fixed count used by the difficulty ramp, so each level strictly contains the previous one
RAMP_EVENTS = {1: 0, 2: 0, 3: 1, 4: 2, 5: 3}
DIFFICULTY_WEIGHTS = {1: 1, 2: 2, 3: 3, 4: 2, 5: 1}
HIDDEN_INTENT_PREFERENCE = ("cancellation_request", "fee_dispute", "refund_status")


def derive_seed(*parts: object) -> int:
    """Stable seed from any values (never Python's hash(), which changes between runs)."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(digest[:12], 16) % MAX_SEED


class ScenarioGenerator:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog

    # ------------------------------------------------------------------ spec building
    def new_spec(self, req: GenerateRequest, seed: int) -> ScenarioSpec:
        rng = random.Random(seed)
        cat = self.catalog

        for key in req.events:
            cat.event(key)  # validates
        if req.focus_skill:
            cat.check_skill(req.focus_skill)

        edge = req.mode in ("multi_event", "rare_event")
        if req.difficulty is not None:
            difficulty = req.difficulty
        else:
            levels = [3, 4, 5] if edge else [1, 2, 3, 4, 5]
            difficulty = rng.choices(levels, weights=[DIFFICULTY_WEIGHTS[x] for x in levels])[0]

        language = req.language or rng.choice(cat.languages)
        gender = req.gender or rng.choice(["F", "M"])
        intent_key = self._pick_intent(req, difficulty, rng)
        events = self._pick_events(req, difficulty, rng, intent_key)

        spec = ScenarioSpec(
            intent=intent_key,
            difficulty=difficulty,
            language=language,
            gender=gender,
            segment=req.segment or self._pick_segment(intent_key, events, rng),
            events=events,
            max_turns=req.max_turns or DEFAULT_MAX_TURNS[difficulty],
            seed=seed,
        )
        return self.normalize_spec(spec, rng)

    def _pick_intent(self, req: GenerateRequest, difficulty: int, rng: random.Random) -> str:
        if req.intent:
            self.catalog.intent(req.intent)
            return req.intent
        pool = list(self.catalog.intents.values())
        if req.focus_skill:
            focused = [i for i in pool if req.focus_skill in i.skills]
            pool = focused or pool
        weights = [1.0 / (1 + abs(i.base_difficulty - difficulty)) for i in pool]
        return rng.choices(pool, weights=weights)[0].key

    def _pick_events(self, req: GenerateRequest, difficulty: int, rng: random.Random, intent_key: str) -> list[str]:
        events = list(dict.fromkeys(req.events))
        low, high = EVENTS_PER_LEVEL[difficulty]
        target = rng.randint(low, high)
        if req.mode == "multi_event":
            target = max(target, 2)
        if req.mode == "rare_event" and not any(self.catalog.event(e).rare for e in events):
            rare_pool = [e for e in self.catalog.events.values() if e.rare]
            events.append(self._weighted_event(rare_pool, req.focus_skill, rng).key)
        pool = [e for e in self.catalog.events.values() if not e.rare and e.key not in events]
        while len(events) < target and pool:
            choice = self._weighted_event(pool, req.focus_skill, rng)
            events.append(choice.key)
            pool = [e for e in pool if e.key != choice.key]
        return events

    @staticmethod
    def _weighted_event(pool, focus_skill, rng):
        weights = [4.0 if focus_skill and focus_skill in e.stresses else 1.0 for e in pool]
        return rng.choices(pool, weights=weights)[0]

    def _pick_segment(self, intent_key: str, events: list[str], rng: random.Random) -> str:
        if "threatens_to_leave" in events:
            return "at_risk"
        return rng.choice(self.catalog.intent(intent_key).typical_segments)

    def normalize_spec(self, spec: ScenarioSpec, rng: random.Random) -> ScenarioSpec:
        """Make the derived fields consistent with the events (used after generating and after mutating)."""
        cat = self.catalog
        cat.intent(spec.intent)
        events = list(dict.fromkeys(spec.events))
        for key in events:
            cat.event(key)

        extra: list[str] = []
        if "second_problem" in events:
            extra = [k for k in spec.extra_intents if k in cat.intents and k != spec.intent][:1]
            if not extra:
                extra = [self._other_intent(spec.intent, rng, avoid_category=cat.intents[spec.intent].category)]
        hidden: str | None = None
        if "hidden_intent" in events:
            if spec.hidden_intent in cat.intents and spec.hidden_intent != spec.intent:
                hidden = spec.hidden_intent
            else:
                preferred = [k for k in HIDDEN_INTENT_PREFERENCE if k in cat.intents and k != spec.intent]
                hidden = rng.choice(preferred) if preferred else self._other_intent(spec.intent, rng)
        return spec.model_copy(update={"events": events, "extra_intents": extra, "hidden_intent": hidden})

    def _other_intent(self, intent_key: str, rng: random.Random, avoid_category: str | None = None) -> str:
        others = [i for i in self.catalog.intents.values() if i.key != intent_key]
        if not others:
            raise CatalogError("at least two intents are needed for second problems and hidden intents")
        different = [i for i in others if i.category != avoid_category]
        return rng.choice(different or others).key

    # ------------------------------------------------------------------ ramp
    def ramp_specs(self, req: RampRequest, seed: int) -> list[ScenarioSpec]:
        rng = random.Random(seed)
        if req.end < req.start:
            raise CatalogError("ramp end must be greater than or equal to start")
        cat = self.catalog
        intent_key = req.intent or rng.choice(sorted(cat.intents))
        cat.intent(intent_key)
        language = req.language or rng.choice(cat.languages)
        gender = req.gender or rng.choice(["F", "M"])
        order = [e.key for e in cat.events.values() if not e.rare]
        rng.shuffle(order)
        ramp_events = order[: max(RAMP_EVENTS.values())]
        segment = rng.choice(cat.intent(intent_key).typical_segments)

        specs = []
        for level in range(req.start, req.end + 1):
            spec = ScenarioSpec(
                intent=intent_key,
                difficulty=level,
                language=language,
                gender=gender,
                segment=segment,
                events=ramp_events[: RAMP_EVENTS[level]],
                max_turns=DEFAULT_MAX_TURNS[level],
                seed=derive_seed(seed, "ramp", level),
            )
            specs.append(self.normalize_spec(spec, random.Random(spec.seed)))
        return specs

    # ------------------------------------------------------------------ assembling the final scenario
    def assemble(
        self,
        spec: ScenarioSpec,
        kind: Kind = "generated",
        parent_id: str | None = None,
        mutation_log: list[str] | None = None,
    ) -> TrainingScenario:
        cat = self.catalog
        intent = cat.intent(spec.intent)
        events = [cat.event(k) for k in spec.events]

        skills = list(intent.skills)
        for event in events:
            for skill in event.stresses:
                if skill not in skills:
                    skills.append(skill)
        criteria = list(intent.success_criteria) + [e.expect for e in events]
        complications = [e.text for e in events]
        if spec.extra_intents:
            second = cat.intent(spec.extra_intents[0])
            complications = [
                f"{e.text} (second problem: {second.title.lower()})" if e.key == "second_problem" else e.text
                for e in events
            ]
        if spec.hidden_intent:
            hidden = cat.intent(spec.hidden_intent)
            complications = [
                f"{e.text} (real need: {hidden.title.lower()})" if e.key == "hidden_intent" else c
                for e, c in zip(events, complications)
            ]

        title = f"{intent.title} (level {spec.difficulty}, {spec.language})"
        if events:
            title += f" + {len(events)} complication{'s' if len(events) > 1 else ''}"

        sim = SimScenario(
            problem_type=spec.intent,
            difficulty=spec.difficulty,
            persona_id=f"{spec.language}_{spec.gender.lower()}",
            language=spec.language,
            gender=spec.gender,
            max_turns=spec.max_turns,
            seed=spec.seed,
        )
        brief = self._brief(spec, intent.title, skills, complications)
        scenario_id = "sc_" + hashlib.sha1(
            f"{spec.model_dump_json()}|{kind}|{parent_id}".encode()
        ).hexdigest()[:10]

        return TrainingScenario(
            id=scenario_id,
            kind=kind,
            parent_id=parent_id,
            mutation_log=list(mutation_log or []),
            title=title,
            category=intent.category,
            opening_emotion=intent.opening_emotion,
            skills=skills,
            success_criteria=criteria,
            complications=complications,
            customer_card=intent.card[spec.language],
            trainer_brief=brief,
            tags=[intent.category, f"level-{spec.difficulty}", spec.language, spec.segment]
            + (["multi-event"] if len(events) >= 2 else [])
            + (["rare-event"] if any(e.rare for e in events) else []),
            spec=spec,
            sim=sim,
            sim_extensions={
                "segment": spec.segment,
                "opening_emotion": intent.opening_emotion,
                "events": list(spec.events),
                "extra_intents": list(spec.extra_intents),
                "hidden_intent": spec.hidden_intent,
            },
        )

    @staticmethod
    def _brief(spec: ScenarioSpec, intent_title: str, skills: list[str], complications: list[str]) -> str:
        text = (
            f"Practise: {intent_title.lower()} with a {spec.segment.replace('_', ' ')} customer "
            f"({spec.language}, difficulty {spec.difficulty}/5). Skills trained: {', '.join(skills)}."
        )
        if complications:
            text += " Complications: " + " ".join(complications)
        return text
