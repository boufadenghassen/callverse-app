"""What-if: change one thing in a scenario and get a new, consistent scenario."""
import random

from .catalog import Catalog
from .generator import DEFAULT_MAX_TURNS, ScenarioGenerator, derive_seed
from .schemas import MutationOp, ScenarioSpec


class MutationError(ValueError):
    pass


def _int(value, name: str, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise MutationError(f"{name} needs an integer value") from None
    if not low <= number <= high:
        raise MutationError(f"{name} must be between {low} and {high}")
    return number


def _choice(value, name: str, allowed) -> str:
    if value not in allowed:
        raise MutationError(f"{name} must be one of {sorted(allowed)}")
    return value


def apply_ops(
    spec: ScenarioSpec, ops: list[MutationOp], generator: ScenarioGenerator, rng: random.Random
) -> tuple[ScenarioSpec, list[str]]:
    """Apply the operations in order. Returns the new spec and a readable log of what changed."""
    cat: Catalog = generator.catalog
    log: list[str] = []
    for item in ops:
        op, value = item.op, item.value
        update: dict = {}

        if op == "harder":
            new_level = min(5, spec.difficulty + 1)
            update = {"difficulty": new_level}
            if len(spec.events) < 3:
                pool = [e.key for e in cat.events.values() if not e.rare and e.key not in spec.events]
                if pool:
                    update["events"] = spec.events + [rng.choice(pool)]
            log.append(f"harder: level {spec.difficulty} -> {new_level}")
        elif op == "easier":
            new_level = max(1, spec.difficulty - 1)
            update = {"difficulty": new_level, "events": spec.events[:-1]}
            log.append(f"easier: level {spec.difficulty} -> {new_level}")
        elif op == "set_difficulty":
            level = _int(value, op, 1, 5)
            update = {"difficulty": level}
            log.append(f"set_difficulty: {level}")
        elif op == "set_language":
            update = {"language": _choice(value, op, cat.languages)}
            log.append(f"set_language: {value}")
        elif op == "set_gender":
            update = {"gender": _choice(value, op, ["F", "M"])}
            log.append(f"set_gender: {value}")
        elif op == "set_intent":
            update = {"intent": _choice(value, op, cat.intents)}
            log.append(f"set_intent: {value}")
        elif op == "set_segment":
            update = {"segment": _choice(value, op, cat.segments)}
            log.append(f"set_segment: {value}")
        elif op == "set_max_turns":
            update = {"max_turns": _int(value, op, 2, 40)}
            log.append(f"set_max_turns: {value}")
        elif op == "add_event":
            key = _choice(value, op, cat.events)
            if key in spec.events:
                raise MutationError(f"event '{key}' is already in the scenario")
            update = {"events": spec.events + [key]}
            log.append(f"add_event: {key}")
        elif op == "remove_event":
            key = _choice(value, op, spec.events)
            update = {"events": [e for e in spec.events if e != key]}
            log.append(f"remove_event: {key}")
        elif op == "add_second_problem":
            events = spec.events if "second_problem" in spec.events else spec.events + ["second_problem"]
            update = {"events": events}
            if value is not None:
                other = _choice(value, op, cat.intents)
                if other == spec.intent:
                    raise MutationError("the second problem must differ from the main intent")
                update["extra_intents"] = [other]
            log.append(f"add_second_problem: {value or 'random'}")
        elif op == "set_hidden_intent":
            other = _choice(value, op, cat.intents)
            if other == spec.intent:
                raise MutationError("the hidden intent must differ from the main intent")
            events = spec.events if "hidden_intent" in spec.events else spec.events + ["hidden_intent"]
            update = {"events": events, "hidden_intent": other}
            log.append(f"set_hidden_intent: {other}")
        elif op == "reseed":
            new_seed = _int(value, op, 0, 2**31 - 1) if value is not None else derive_seed(spec.seed, "reseed", len(log))
            update = {"seed": new_seed}
            log.append(f"reseed: {new_seed}")

        # changing the main intent invalidates the derived second and hidden intents
        if "intent" in update:
            update.setdefault("extra_intents", [])
            update.setdefault("hidden_intent", None)
        spec = spec.model_copy(update=update)
        spec = generator.normalize_spec(spec, rng)
        if "set_max_turns" not in log[-1] and op in ("harder", "easier", "set_difficulty") and spec.max_turns in DEFAULT_MAX_TURNS.values():
            # keep the default length in line with the level, unless the user fixed it
            spec = spec.model_copy(update={"max_turns": DEFAULT_MAX_TURNS[spec.difficulty]})
    return spec, log


def random_ops(spec: ScenarioSpec, generator: ScenarioGenerator, rng: random.Random) -> list[MutationOp]:
    """One or two random what-if changes that are valid for this spec."""
    cat = generator.catalog
    candidates: list[MutationOp] = [
        MutationOp(op="harder"),
        MutationOp(op="easier"),
        MutationOp(op="set_language", value=rng.choice([x for x in cat.languages if x != spec.language])),
        MutationOp(op="set_gender", value="M" if spec.gender == "F" else "F"),
        MutationOp(op="set_intent", value=rng.choice([k for k in cat.intents if k != spec.intent])),
        MutationOp(op="set_segment", value=rng.choice([s for s in cat.segments if s != spec.segment])),
        MutationOp(op="add_second_problem"),
        MutationOp(op="reseed"),
    ]
    pool = [e for e in cat.events if e not in spec.events]
    if pool:
        candidates.append(MutationOp(op="add_event", value=rng.choice(pool)))
    if spec.events:
        candidates.append(MutationOp(op="remove_event", value=rng.choice(spec.events)))
    if spec.difficulty == 5:
        candidates = [c for c in candidates if c.op != "harder"]
    if spec.difficulty == 1:
        candidates = [c for c in candidates if c.op != "easier"]
    return rng.sample(candidates, k=rng.choice([1, 2]))
