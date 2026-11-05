import pytest

from scenario_gen.catalog import CatalogError
from scenario_gen.schemas import BatchRequest, GenerateRequest, RampRequest
from scenario_gen.service import BadRequest


def test_same_seed_gives_identical_scenario(service):
    a = service.generate(GenerateRequest(seed=123))
    b = service.generate(GenerateRequest(seed=123))
    assert a.model_dump() == b.model_dump()


def test_different_seeds_give_variety(service):
    ids = {service.generate(GenerateRequest(seed=s)).id for s in range(40)}
    assert len(ids) > 30


def test_requested_fields_are_respected(service):
    s = service.generate(
        GenerateRequest(intent="line_cut", difficulty=4, language="fr", gender="F", max_turns=20, seed=1)
    )
    assert (s.sim.problem_type, s.sim.difficulty, s.sim.language, s.sim.gender, s.sim.max_turns) == (
        "line_cut", 4, "fr", "F", 20,
    )
    assert s.customer_card.startswith("Votre ligne")


def test_card_follows_the_language(service):
    cards = {
        lang: service.generate(GenerateRequest(intent="double_billing", language=lang, seed=1)).customer_card
        for lang in ("en", "fr", "derja")
    }
    assert len(set(cards.values())) == 3


def test_unknown_intent_is_a_bad_request(service):
    with pytest.raises(BadRequest):
        service.generate(GenerateRequest(intent="does_not_exist"))


def test_unknown_event_and_skill_are_bad_requests(service):
    with pytest.raises(BadRequest):
        service.generate(GenerateRequest(events=["nope"]))
    with pytest.raises(BadRequest):
        service.generate(GenerateRequest(focus_skill="telepathy"))


def test_forced_events_are_kept(service):
    s = service.generate(GenerateRequest(difficulty=1, events=["time_pressure"], seed=4))
    assert "time_pressure" in s.spec.events


def test_difficulty_one_has_no_complications_by_default(service):
    for seed in range(20):
        assert service.generate(GenerateRequest(difficulty=1, seed=seed)).spec.events == []


def test_multi_event_mode_has_at_least_two_events(service):
    for seed in range(20):
        s = service.generate(GenerateRequest(mode="multi_event", seed=seed))
        assert len(s.spec.events) >= 2
        assert "multi-event" in s.tags


def test_rare_event_mode_includes_a_rare_event(service):
    for seed in range(20):
        s = service.generate(GenerateRequest(mode="rare_event", seed=seed))
        assert any(service.catalog.event(e).rare for e in s.spec.events)
        assert "rare-event" in s.tags


def test_second_problem_and_hidden_intent_are_consistent(service):
    s = service.generate(GenerateRequest(intent="plan_change", events=["second_problem", "hidden_intent"], seed=3))
    assert len(s.spec.extra_intents) == 1 and s.spec.extra_intents[0] != "plan_change"
    assert s.spec.hidden_intent and s.spec.hidden_intent != "plan_change"
    assert any("second problem" in c for c in s.complications)
    assert any("real need" in c for c in s.complications)
    plain = service.generate(GenerateRequest(intent="plan_change", events=["time_pressure"], seed=3))
    assert plain.spec.extra_intents == [] and plain.spec.hidden_intent is None


def test_threat_to_leave_makes_an_at_risk_customer(service):
    s = service.generate(GenerateRequest(events=["threatens_to_leave"], seed=2))
    assert s.spec.segment == "at_risk"


def test_focus_skill_steers_the_intent(service):
    skill = "escalation_handling"
    for seed in range(15):
        s = service.generate(GenerateRequest(focus_skill=skill, seed=seed))
        assert skill in s.skills


def test_skills_include_those_of_the_events(service):
    s = service.generate(GenerateRequest(intent="data_allowance_question", events=["asks_for_supervisor"], seed=1))
    assert "escalation_handling" in s.skills
    assert any("escalation" in c.lower() or "supervisor" in c.lower() or "escalat" in c.lower() for c in s.success_criteria)


def test_ids_are_stable_and_unique_per_content(service):
    a = service.generate(GenerateRequest(seed=1))
    b = service.generate(GenerateRequest(seed=2))
    assert a.id.startswith("sc_") and a.id != b.id


def test_batch_covers_intents_and_languages(service):
    out = service.batch(BatchRequest(count=15, seed=8))
    assert len({s.spec.intent for s in out}) == 15  # every intent before any repeat
    assert {s.spec.language for s in out} == {"en", "fr", "derja"}


def test_batch_respects_difficulty_range_and_languages(service):
    out = service.batch(BatchRequest(count=20, difficulty_min=2, difficulty_max=3, languages=["fr"], seed=5))
    assert {s.spec.difficulty for s in out} <= {2, 3}
    assert {s.spec.language for s in out} == {"fr"}


def test_batch_is_reproducible(service):
    a = [s.id for s in service.batch(BatchRequest(count=8, seed=77))]
    b = [s.id for s in service.batch(BatchRequest(count=8, seed=77))]
    assert a == b


def test_batch_bad_range(service):
    with pytest.raises(BadRequest):
        service.batch(BatchRequest(count=3, difficulty_min=4, difficulty_max=2))


def test_ramp_gets_harder_and_keeps_the_same_situation(service):
    ramp = service.ramp(RampRequest(intent="slow_internet", language="fr", seed=6))
    assert [s.spec.difficulty for s in ramp] == [1, 2, 3, 4, 5]
    assert len({s.spec.intent for s in ramp}) == 1
    assert len({s.spec.language for s in ramp}) == 1
    sizes = [len(s.spec.events) for s in ramp]
    assert sizes == sorted(sizes) and sizes[0] == 0 and sizes[-1] == 3
    for easy, hard in zip(ramp, ramp[1:]):
        assert set(easy.spec.events) <= set(hard.spec.events)
    assert all(s.kind == "ramp" for s in ramp)


def test_ramp_partial_and_invalid(service):
    assert [s.spec.difficulty for s in service.ramp(RampRequest(start=3, end=4, seed=1))] == [3, 4]
    with pytest.raises(BadRequest):
        service.ramp(RampRequest(start=4, end=2))


def test_generator_new_spec_rejects_unknown_intent_directly(generator):
    with pytest.raises(CatalogError):
        generator.new_spec(GenerateRequest(intent="zzz"), 1)
