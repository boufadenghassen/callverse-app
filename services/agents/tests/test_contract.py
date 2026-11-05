"""The most important tests: what we send must be accepted by the Customer Sim's own schema."""
from scenario_gen.schemas import BatchRequest, GenerateRequest, RampRequest, SimScenario


def test_sim_fields_match_customer_sim_scenario(sim_schemas):
    ours = SimScenario.model_fields
    theirs = sim_schemas.Scenario.model_fields
    assert list(ours) == list(theirs)
    for name in theirs:
        assert ours[name].annotation == theirs[name].annotation, name


def test_every_kind_of_scenario_validates_against_customer_sim_schema(service, sim_schemas):
    scenarios = []
    scenarios += service.batch(BatchRequest(count=30, seed=1))
    scenarios += service.batch(BatchRequest(count=12, seed=2, mode="multi_event"))
    scenarios += service.batch(BatchRequest(count=12, seed=3, mode="rare_event"))
    scenarios += service.ramp(RampRequest(seed=4))
    scenarios.append(service.generate(GenerateRequest(seed=5)))
    for scenario in scenarios:
        parsed = sim_schemas.Scenario.model_validate(scenario.sim.model_dump())
        assert parsed.problem_type == scenario.spec.intent
        assert parsed.persona_id == f"{parsed.language}_{parsed.gender.lower()}"
        assert parsed.seed == scenario.spec.seed


def test_persona_id_pattern_matches_the_example_of_the_sim(service):
    scenario = service.generate(GenerateRequest(language="derja", gender="M", seed=1))
    assert scenario.sim.persona_id == "derja_m"


def test_extensions_are_outside_the_contract(service):
    scenario = service.generate(GenerateRequest(difficulty=5, seed=9))
    assert "events" not in scenario.sim.model_dump()
    assert "events" in scenario.sim_extensions
