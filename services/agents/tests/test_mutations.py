import pytest

from scenario_gen.schemas import GenerateRequest, MutateRequest, MutationOp
from scenario_gen.service import BadRequest
from scenario_gen.store import ScenarioNotFound


def base(service, **kw):
    kw.setdefault("seed", 10)
    kw.setdefault("intent", "double_billing")
    kw.setdefault("difficulty", 2)
    kw.setdefault("language", "en")
    return service.generate(GenerateRequest(**kw))


def mutate(service, scenario, *ops, **kw):
    return service.mutate(scenario.id, MutateRequest(ops=[MutationOp(**o) for o in ops], **kw))


def test_replay_is_identical(service):
    original = base(service)
    again = service.replay(original.id)
    assert again.model_dump() == original.model_dump()
    assert again.sim.seed == original.sim.seed


def test_replay_with_reseed_keeps_the_situation_but_changes_the_seed(service):
    original = base(service, events=["time_pressure"])
    new = service.replay(original.id, reseed=True)
    assert new.kind == "replay" and new.parent_id == original.id
    assert new.spec.intent == original.spec.intent and new.spec.events == original.spec.events
    assert new.sim.seed != original.sim.seed
    assert service.get(new.id) == new


def test_replay_unknown_id(service):
    with pytest.raises(ScenarioNotFound):
        service.replay("sc_missing")


def test_harder_raises_difficulty_and_adds_a_complication(service):
    original = base(service)
    harder = mutate(service, original, {"op": "harder"})
    assert harder.spec.difficulty == 3 and len(harder.spec.events) == len(original.spec.events) + 1
    assert harder.kind == "mutation" and harder.parent_id == original.id
    assert harder.mutation_log and harder.mutation_log[0].startswith("harder")


def test_harder_caps_at_five_and_easier_floors_at_one(service):
    top = base(service, difficulty=5)
    assert mutate(service, top, {"op": "harder"}).spec.difficulty == 5
    bottom = base(service, difficulty=1)
    assert mutate(service, bottom, {"op": "easier"}).spec.difficulty == 1


def test_changing_language_changes_card_and_persona(service):
    out = mutate(service, base(service), {"op": "set_language", "value": "derja"}, {"op": "set_gender", "value": "M"})
    assert out.sim.persona_id == "derja_m"
    assert out.customer_card != base(service).customer_card


def test_changing_intent_resets_second_and_hidden_intent(service):
    original = base(service, events=["second_problem", "hidden_intent"])
    assert original.spec.extra_intents and original.spec.hidden_intent
    out = mutate(service, original, {"op": "set_intent", "value": "cancellation_request"})
    assert out.spec.intent == "cancellation_request"
    assert out.spec.extra_intents[0] != "cancellation_request"
    assert out.spec.hidden_intent != "cancellation_request"


def test_add_and_remove_event(service):
    original = base(service, difficulty=1)
    added = mutate(service, original, {"op": "add_event", "value": "asks_for_supervisor"})
    assert "asks_for_supervisor" in added.spec.events and "escalation_handling" in added.skills
    removed = mutate(service, added, {"op": "remove_event", "value": "asks_for_supervisor"})
    assert removed.spec.events == []


def test_add_second_problem_with_a_chosen_intent(service):
    out = mutate(service, base(service), {"op": "add_second_problem", "value": "slow_internet"})
    assert out.spec.extra_intents == ["slow_internet"] and "second_problem" in out.spec.events


def test_set_hidden_intent(service):
    out = mutate(service, base(service), {"op": "set_hidden_intent", "value": "cancellation_request"})
    assert out.spec.hidden_intent == "cancellation_request"


@pytest.mark.parametrize(
    "op",
    [
        {"op": "set_difficulty", "value": 9},
        {"op": "set_difficulty", "value": "abc"},
        {"op": "set_language", "value": "de"},
        {"op": "set_intent", "value": "nope"},
        {"op": "add_event", "value": "nope"},
        {"op": "remove_event", "value": "time_pressure"},
        {"op": "add_second_problem", "value": "double_billing"},
        {"op": "set_hidden_intent", "value": "double_billing"},
        {"op": "set_max_turns", "value": 1},
    ],
)
def test_invalid_operations_are_bad_requests(service, op):
    with pytest.raises(BadRequest):
        mutate(service, base(service), op)


def test_adding_the_same_event_twice_fails(service):
    original = base(service, events=["time_pressure"])
    with pytest.raises(BadRequest):
        mutate(service, original, {"op": "add_event", "value": "time_pressure"})


def test_mutation_needs_something_to_do(service):
    with pytest.raises(BadRequest):
        service.mutate(base(service).id, MutateRequest())


def test_random_mutation_is_valid_and_reproducible(service):
    original = base(service, difficulty=3, events=["time_pressure"])
    a = service.mutate(original.id, MutateRequest(random=True, seed=5))
    b = service.mutate(original.id, MutateRequest(random=True, seed=5))
    assert a.model_dump() == b.model_dump()
    assert a.spec != original.spec and a.parent_id == original.id
    for seed in range(40):  # never produces an invalid scenario
        service.mutate(original.id, MutateRequest(random=True, seed=seed))


def test_lineage_lists_ancestors_oldest_first(service):
    a = base(service)
    b = mutate(service, a, {"op": "harder"})
    c = mutate(service, b, {"op": "set_language", "value": "fr"})
    assert [s.id for s in service.lineage(c.id)] == [a.id, b.id, c.id]


def test_set_max_turns_survives_and_default_turns_follow_difficulty(service):
    original = base(service, difficulty=2)
    assert mutate(service, original, {"op": "set_difficulty", "value": 5}).spec.max_turns == 16
    fixed = mutate(service, original, {"op": "set_max_turns", "value": 7})
    assert fixed.spec.max_turns == 7
