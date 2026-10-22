"""Adaptive training: Quality Analyst weaknesses -> skills to train -> a plan of scenarios.

Input format is a placeholder until the Quality Agent's real output exists: a list of
{criterion, score}. Criterion names are matched leniently (French or English, or a skill name). If the
Quality Agent changes its format, only `normalize_weaknesses` needs to change.
"""
import random

from .catalog import Catalog
from .generator import ScenarioGenerator, derive_seed
from .schemas import (
    FocusItem,
    GenerateRequest,
    ProgressItem,
    ProgressReport,
    QAWeakness,
    TrainingPlan,
    TrainingPlanRequest,
    TrainingScenario,
)


def to_unit_scale(score: float) -> float:
    """0 to 1 stays as is, anything above 1 is read as a percentage."""
    return score if score <= 1 else score / 100.0


def normalize_weaknesses(
    catalog: Catalog, weaknesses: list[QAWeakness], threshold: float
) -> tuple[dict[str, FocusItem], list[str]]:
    """Return the skill gaps (only for scores under the threshold) and notes about ignored criteria."""
    gaps: dict[str, FocusItem] = {}
    notes: list[str] = []
    for item in weaknesses:
        mapping = catalog.criterion_to_skills(item.criterion)
        if mapping is None:
            notes.append(f"Ignored unknown QA criterion '{item.criterion}'.")
            continue
        score = to_unit_scale(item.score)
        if score >= threshold:
            continue
        severity = 1.0 - score
        for skill, weight in mapping:
            gap = round(severity * weight, 3)
            focus = gaps.get(skill)
            if focus is None:
                gaps[skill] = FocusItem(skill=skill, gap=gap, criteria=[item.criterion])
            else:
                focus.gap = max(focus.gap, gap)
                if item.criterion not in focus.criteria:
                    focus.criteria.append(item.criterion)
    return gaps, notes


def allocate(gaps: list[FocusItem], size: int) -> dict[str, int]:
    """Split `size` scenarios between skills, proportionally to the gaps, at least one each when possible."""
    if not gaps:
        return {}
    if size < len(gaps):
        gaps = gaps[:size]
    counts = {g.skill: 1 for g in gaps}
    remaining = size - len(gaps)
    total = sum(g.gap for g in gaps) or 1.0
    shares = sorted(gaps, key=lambda g: g.gap, reverse=True)
    for g in shares:
        extra = int(remaining * g.gap / total)
        counts[g.skill] += extra
    leftover = size - sum(counts.values())
    i = 0
    while leftover > 0:
        counts[shares[i % len(shares)].skill] += 1
        leftover -= 1
        i += 1
    return counts


def build_plan(req: TrainingPlanRequest, generator: ScenarioGenerator) -> TrainingPlan:
    cat = generator.catalog
    gaps, notes = normalize_weaknesses(cat, req.weaknesses, req.threshold)
    ranked = sorted(gaps.values(), key=lambda g: g.gap, reverse=True)[: req.max_skills]

    if not ranked:
        rationale = notes + [
            f"No QA score is under {req.threshold:.0%}: no weakness to train. "
            "Maintenance suggestion: one rare-event scenario to keep the advisor sharp."
        ]
        base = req.seed if req.seed is not None else derive_seed(req.advisor_id, "maintenance")
        scenario = generator.assemble(
            generator.new_spec(
                GenerateRequest(mode="rare_event", difficulty=min(5, req.current_level + 1), seed=base), base
            ),
            kind="adaptive",
        )
        return TrainingPlan(
            advisor_id=req.advisor_id, needs_training=False, focus=[], scenarios=[scenario], rationale=rationale
        )

    counts = allocate(ranked, req.size)
    base_seed = req.seed if req.seed is not None else derive_seed(req.advisor_id, [g.skill for g in ranked])
    languages = req.languages or cat.languages
    scenarios: list[TrainingScenario] = []
    rationale = list(notes)
    index = 0
    for focus in ranked:
        n = counts.get(focus.skill, 0)
        if n == 0:
            continue
        rationale.append(
            f"{focus.skill}: gap {focus.gap:.2f} (from {', '.join(focus.criteria)}); "
            f"{n} scenario{'s' if n > 1 else ''}, ramping from level {req.current_level}."
        )
        for step in range(n):
            # ramp: first scenario at the advisor's level, then up to two levels higher
            level = min(5, req.current_level + (0 if n == 1 else round(2 * step / (n - 1))))
            seed = derive_seed(base_seed, focus.skill, step)
            gen_req = GenerateRequest(
                difficulty=level,
                language=languages[index % len(languages)],
                focus_skill=focus.skill,
                seed=seed,
            )
            spec = generator.new_spec(gen_req, seed)
            scenarios.append(generator.assemble(spec, kind="adaptive"))
            index += 1
    return TrainingPlan(
        advisor_id=req.advisor_id, needs_training=True, focus=ranked, scenarios=scenarios, rationale=rationale
    )


def compare_progress(before: list[QAWeakness], after: list[QAWeakness], tolerance: float = 0.02) -> ProgressReport:
    """Did the scores move between two QA reports? Matched by normalized criterion name."""
    from .catalog import normalize_key

    def index(items: list[QAWeakness]) -> dict[str, tuple[str, float]]:
        return {normalize_key(i.criterion): (i.criterion, to_unit_scale(i.score)) for i in items}

    old, new = index(before), index(after)
    rows: list[ProgressItem] = []
    for key in sorted(set(old) & set(new)):
        name, b = old[key]
        _, a = new[key]
        delta = round(a - b, 4)
        status = "improved" if delta > tolerance else "regressed" if delta < -tolerance else "unchanged"
        rows.append(ProgressItem(criterion=name, before=round(b, 4), after=round(a, 4), delta=delta, status=status))
    return ProgressReport(
        items=rows,
        improved=sum(r.status == "improved" for r in rows),
        regressed=sum(r.status == "regressed" for r in rows),
        unchanged=sum(r.status == "unchanged" for r in rows),
    )
