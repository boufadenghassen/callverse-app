"""Constrained reinforcement-learning policy for workforce allocation.

The policy is deliberately isolated from the HTTP layer.  It bootstraps from
the deterministic routing simulator, learns a Q-table with temporal-difference
updates, and never applies an action without the safety guard.  The current
deployment mode is shadow: callers receive a proposed plan and the fallback
plan, but the existing schedule is not mutated.

The module is dependency-light so the local demo works without a training
platform.  The persisted decision schema is compatible with replacing the
Q-table trainer with RLlib or another registered policy later.
"""
from __future__ import annotations

import random
from functools import lru_cache

import routing
import workforce as wf
import workforce_data as data

MAX_STEPS = 6
EPISODES = 800
SEED = 41
LEARNING_RATE = 0.18
DISCOUNT = 0.92
EPSILON_START = 0.30
EPSILON_END = 0.03
MIN_REWARD = 0.05

ACTION_PAIRS = tuple(
    (source, target)
    for source, targets in routing.CROSS_SKILLS.items()
    for target in targets
)
NOOP = -1


@lru_cache(maxsize=1)
def _real_calls() -> dict[int, dict[str, int]]:
    return data.real_calls_by_hour()


def _calls(hour: int) -> dict[str, int]:
    """Use ingested real-derived scenarios when present, with explicit fallback."""
    real = _real_calls().get(hour)
    if real:
        return real
    return {
        queue: next(point["forecast"] for point in wf.forecast(queue) if point["hour"] == f"{hour}h")
        for queue in wf.QUEUES
    }


def _initial_counts(hour: int) -> tuple[int, ...]:
    duty = routing.on_duty(hour)
    counts = {queue: 0 for queue in wf.QUEUES}
    for advisor in duty:
        counts[advisor["primary"]] += 1
    return tuple(counts[queue] for queue in wf.QUEUES)


def _as_counts(values: tuple[int, ...]) -> dict[str, int]:
    return dict(zip(wf.QUEUES, values))


def _state(hour: int, counts: tuple[int, ...], step: int) -> tuple[int, tuple[int, ...], int]:
    return hour, counts, step


def valid_actions(counts: tuple[int, ...]) -> tuple[int, ...]:
    """Return action indexes that are structurally valid for this allocation."""
    valid = [NOOP]
    for index, (source, _target) in enumerate(ACTION_PAIRS):
        source_index = tuple(wf.QUEUES).index(source)
        if counts[source_index] > 0:
            valid.append(index)
    return tuple(valid)


def apply_action(hour: int, counts: tuple[int, ...], action: int) -> tuple[int, ...] | None:
    """Apply one masked move, or return None for an invalid action."""
    if action == NOOP:
        return counts
    if action < 0 or action >= len(ACTION_PAIRS):
        return None
    source, target = ACTION_PAIRS[action]
    values = list(counts)
    source_index, target_index = tuple(wf.QUEUES).index(source), tuple(wf.QUEUES).index(target)
    if values[source_index] <= 0:
        return None
    calls = _calls(hour)
    before_source = wf.stats(calls[source], wf.QUEUES[source]["aht"], values[source_index])["sla"]
    values[source_index] -= 1
    values[target_index] += 1
    after_source = wf.stats(calls[source], wf.QUEUES[source]["aht"], values[source_index])["sla"]
    floor = min(routing.GUARD, before_source)
    if after_source < floor - 1e-9:
        return None
    return tuple(values)


def _apply_action_for_calls(hour: int, counts: tuple[int, ...], action: int, calls: dict[str, int]) -> tuple[int, ...] | None:
    """Apply the same constrained action mask against an evaluation scenario."""
    if action == NOOP:
        return counts
    if action < 0 or action >= len(ACTION_PAIRS):
        return None
    source, target = ACTION_PAIRS[action]
    values = list(counts)
    source_index, target_index = tuple(wf.QUEUES).index(source), tuple(wf.QUEUES).index(target)
    if values[source_index] <= 0:
        return None
    before = wf.stats(calls[source], wf.QUEUES[source]["aht"], values[source_index])
    values[source_index] -= 1
    values[target_index] += 1
    after = wf.stats(calls[source], wf.QUEUES[source]["aht"], values[source_index])
    if after["sla"] < min(routing.GUARD, before["sla"]) - 1e-9:
        return None
    return tuple(values)


def _reward(hour: int, before: tuple[int, ...], after: tuple[int, ...]) -> float:
    calls = _calls(hour)
    gain = routing.objective(calls, _as_counts(after)) - routing.objective(calls, _as_counts(before))
    return gain


def _choose(q_values: dict[tuple, float], state: tuple, actions: tuple[int, ...], rng: random.Random, epsilon: float) -> int:
    if rng.random() < epsilon:
        return rng.choice(actions)
    return max(actions, key=lambda action: q_values.get((state, action), 0.0))


@lru_cache(maxsize=1)
def train() -> dict:
    """Train the policy on the deterministic bootstrap simulator."""
    rng = random.Random(SEED)
    q_values: dict[tuple, float] = {}
    hours = [hour for hour in wf.HOURS if hour > wf.NOW_HOUR]
    for episode in range(EPISODES):
        hour = rng.choice(hours)
        counts = _initial_counts(hour)
        for step in range(MAX_STEPS):
            state = _state(hour, counts, step)
            actions = valid_actions(counts)
            progress = episode / max(1, EPISODES - 1)
            epsilon = EPSILON_START + (EPSILON_END - EPSILON_START) * progress
            action = _choose(q_values, state, actions, rng, epsilon)
            next_counts = apply_action(hour, counts, action)
            if next_counts is None:
                q_values[(state, action)] = -1.0
                break
            reward = _reward(hour, counts, next_counts)
            next_state = _state(hour, next_counts, step + 1)
            next_actions = valid_actions(next_counts)
            future = max((q_values.get((next_state, candidate), 0.0) for candidate in next_actions), default=0.0)
            old = q_values.get((state, action), 0.0)
            q_values[(state, action)] = old + LEARNING_RATE * (reward + DISCOUNT * future - old)
            counts = next_counts
            if action == NOOP or reward < MIN_REWARD:
                break
    return {"qValues": q_values, "episodes": EPISODES, "seed": SEED}


def _policy_action(hour: int, counts: tuple[int, ...], step: int) -> tuple[int, tuple[int, ...], float]:
    learned = train()["qValues"]
    state = _state(hour, counts, step)
    actions = valid_actions(counts)
    action = max(actions, key=lambda candidate: learned.get((state, candidate), 0.0))
    next_counts = apply_action(hour, counts, action)
    value = learned.get((state, action), 0.0)
    if next_counts is None or value < MIN_REWARD:
        return NOOP, counts, value
    return action, next_counts, value


def _decision(hour: int) -> dict:
    calls = _calls(hour)
    baseline = routing.allocate(hour)
    counts = _initial_counts(hour)
    moves = []
    for step in range(MAX_STEPS):
        action, next_counts, value = _policy_action(hour, counts, step)
        if action == NOOP:
            break
        source, target = ACTION_PAIRS[action]
        before = wf.stats(calls[source], wf.QUEUES[source]["aht"], counts[tuple(wf.QUEUES).index(source)])
        after = wf.stats(calls[source], wf.QUEUES[source]["aht"], next_counts[tuple(wf.QUEUES).index(source)])
        if after["sla"] < min(routing.GUARD, before["sla"]) - 1e-9:
            break
        moves.append({
            "action": "reassign",
            "fromQueue": source,
            "toQueue": target,
            "value": round(value, 3),
            "text": f"RL policy proposes moving one cross-skilled advisor from queue {source} to queue {target} at {hour}h.",
        })
        counts = next_counts
    return {
        "hour": f"{hour}h",
        "moves": moves,
        "baseline": baseline,
        "recommendedCounts": _as_counts(counts),
        "masked": True,
        "safetyChecked": True,
    }


@lru_cache(maxsize=1)
def shadow_plan() -> dict:
    """Return RL recommendations beside the unchanged deterministic fallback."""
    decisions = [_decision(hour) for hour in wf.HOURS if hour > wf.NOW_HOUR]
    return {
        "mode": "shadow",
        "policy": "q-learning-bootstrap-v1",
        "training": {key: value for key, value in train().items() if key != "qValues"},
        "fallback": routing.plan(),
        "hours": decisions,
        "method": "Constrained Q-learning trained on the workforce discrete-event bootstrap simulator; recommendations are shadow-only.",
    }


def health() -> dict:
    learned = train()
    return {
        "status": "ready",
        "policy": "q-learning-bootstrap-v1",
        "mode": "shadow",
        "episodes": learned["episodes"],
        "seed": learned["seed"],
        "actions": len(ACTION_PAIRS) + 1,
        "hardConstraints": ["skill eligibility", "protected donor service level", "bounded moves"],
        "dataset": data.seed_summary(),
    }


def _scenario_objective(calls: dict[str, int], counts: tuple[int, ...]) -> float:
    return routing.objective(calls, _as_counts(counts))


def evaluate_scenarios() -> dict:
    """Evaluate the learned policy against real-derived demand stress cases."""
    results = []
    for scenario in data.real_scenarios():
        scenario_results = []
        for hour in (14, 15, 16, 17):
            calls = scenario["calls"][hour]
            baseline = _initial_counts(hour)
            counts = baseline
            moves = 0
            safe = True
            for step in range(MAX_STEPS):
                state = _state(hour, counts, step)
                actions = valid_actions(counts)
                learned = train()["qValues"]
                action = max(actions, key=lambda candidate: learned.get((state, candidate), 0.0))
                next_counts = _apply_action_for_calls(hour, counts, action, calls)
                if action == NOOP or next_counts is None:
                    if action != NOOP:
                        safe = False
                    break
                counts = next_counts
                moves += 1
            baseline_score = _scenario_objective(calls, baseline)
            rl_score = _scenario_objective(calls, counts)
            scenario_results.append({
                "hour": f"{hour}h",
                "baselineScore": round(baseline_score, 2),
                "rlScore": round(rl_score, 2),
                "improvement": round(rl_score - baseline_score, 2),
                "moves": moves,
                "safe": safe,
            })
        results.append({
            "name": scenario["name"],
            "description": scenario["description"],
            "source": scenario["source"],
            "hours": scenario_results,
            "baselineScore": round(sum(row["baselineScore"] for row in scenario_results), 2),
            "rlScore": round(sum(row["rlScore"] for row in scenario_results), 2),
            "meetsBaseline": all(row["rlScore"] >= row["baselineScore"] for row in scenario_results),
            "safe": all(row["safe"] for row in scenario_results),
        })
    promotion_ready = all(scenario["meetsBaseline"] and scenario["safe"] for scenario in results)
    return {
        "policy": "q-learning-bootstrap-v1",
        "mode": "shadow",
        "dataset": data.seed_summary(),
        "scenarios": results,
        "promotionReady": promotion_ready,
        "method": "Evaluation on real-derived demand with documented stress transformations; RL remains shadow-only.",
    }
