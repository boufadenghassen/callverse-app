import json

import httpx
import pytest
from fastapi.testclient import TestClient

from scenario_gen.catalog import Catalog
from scenario_gen.config import Settings
from scenario_gen.llm import LLMClient, clean_text, parse_json_object
from scenario_gen.schemas import (
    GenerateRequest,
    ProgressRequest,
    QAWeakness,
    TrainingPlanRequest,
)
from scenario_gen.service import ScenarioService
from scenario_gen.store import ScenarioStore


# ----------------------------------------------------------------------------- adaptive training
def plan_req(**kw):
    kw.setdefault("advisor_id", "adv1")
    kw.setdefault("seed", 1)
    return TrainingPlanRequest(**kw)


def test_plan_targets_the_weakest_skills(service):
    weaknesses = [
        QAWeakness(criterion="Sentiment", score=0.3),
        QAWeakness(criterion="Conformité", score=55),
        QAWeakness(criterion="Exactitude", score=92),
    ]
    plan = service.plan(plan_req(weaknesses=weaknesses, size=6))
    assert plan.needs_training
    skills = [f.skill for f in plan.focus]
    assert skills[0] in ("empathy", "de_escalation")  # sentiment is the weakest criterion
    assert "procedure_compliance" in skills
    assert "accuracy" not in skills  # 92% is above the threshold
    assert len(plan.scenarios) == 6
    for scenario in plan.scenarios:
        assert scenario.kind == "adaptive"
        assert any(s in skills for s in scenario.skills)
        assert service.get(scenario.id) == scenario  # saved, so it can be replayed


def test_plan_ramps_difficulty_from_the_current_level(service):
    weaknesses = [QAWeakness(criterion="accuracy", score=0.2)]
    plan = service.plan(plan_req(weaknesses=weaknesses, size=5, current_level=2))
    levels = [s.spec.difficulty for s in plan.scenarios]
    assert levels[0] == 2 and levels[-1] == 4 and levels == sorted(levels)


def test_plan_languages_rotate(service):
    plan = service.plan(
        plan_req(weaknesses=[QAWeakness(criterion="sentiment", score=0.1)], size=4, languages=["fr", "derja"])
    )
    assert {s.spec.language for s in plan.scenarios} == {"fr", "derja"}


def test_plan_without_weakness_proposes_maintenance(service):
    plan = service.plan(plan_req(weaknesses=[QAWeakness(criterion="accuracy", score=0.95)]))
    assert not plan.needs_training and plan.focus == []
    assert len(plan.scenarios) == 1 and any("rare-event" == t for t in plan.scenarios[0].tags)


def test_unknown_criterion_is_reported_not_fatal(service):
    plan = service.plan(
        plan_req(weaknesses=[QAWeakness(criterion="charisma", score=0.1), QAWeakness(criterion="accuracy", score=0.1)])
    )
    assert plan.needs_training
    assert any("charisma" in r for r in plan.rationale)


def test_plan_is_reproducible_and_size_is_exact(service):
    w = [QAWeakness(criterion="sentiment", score=0.2), QAWeakness(criterion="compliance", score=0.4)]
    a = service.plan(plan_req(weaknesses=w, size=7))
    b = service.plan(plan_req(weaknesses=w, size=7))
    assert [s.id for s in a.scenarios] == [s.id for s in b.scenarios]
    assert len(a.scenarios) == 7
    small = service.plan(plan_req(weaknesses=w, size=1))
    assert len(small.scenarios) == 1


def test_progress_report(service):
    report = service.progress(
        ProgressRequest(
            before=[QAWeakness(criterion="Sentiment", score=40), QAWeakness(criterion="Exactitude", score=80),
                    QAWeakness(criterion="Pertinence", score=60)],
            after=[QAWeakness(criterion="sentiment", score=0.7), QAWeakness(criterion="exactitude", score=0.6),
                   QAWeakness(criterion="pertinence", score=0.6)],
        )
    )
    status = {i.criterion: i.status for i in report.items}
    assert status == {"Sentiment": "improved", "Exactitude": "regressed", "Pertinence": "unchanged"}
    assert (report.improved, report.regressed, report.unchanged) == (1, 1, 1)


# ----------------------------------------------------------------------------- store
def test_store_persists_to_a_jsonl_file(tmp_path, catalog):
    path = tmp_path / "history" / "scenarios.jsonl"
    first = ScenarioService(catalog, ScenarioStore(path))
    scenario = first.generate(GenerateRequest(seed=3))
    first.generate(GenerateRequest(seed=3))  # same scenario again: not written twice
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1
    second = ScenarioService(catalog, ScenarioStore(path))
    assert second.get(scenario.id) == scenario


def test_store_filters(service):
    for seed in range(6):
        service.generate(GenerateRequest(seed=seed, language="fr" if seed % 2 else "en"))
    assert all(s.spec.language == "fr" for s in service.store.find(language="fr"))
    assert len(service.store.find(limit=2)) == 2


# ----------------------------------------------------------------------------- LLM
def settings(key="test-key"):
    return Settings(
        openrouter_api_key=key,
        openrouter_model="test/model",
        openrouter_base_url="https://example.test/api/v1",
        llm_timeout=5,
        store_path=None,
        sim_intents_path=None,
    )


def fake_llm(handler, key="test-key"):
    return LLMClient(settings(key), transport=httpx.MockTransport(handler))


def ok_handler(captured=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        body = {"choices": [{"message": {"content": json.dumps(
            {"customer_card": "Vous êtes très en colère contre cette double facture.", "trainer_brief": "Practise de-escalation."},
            ensure_ascii=False)}}]}
        return httpx.Response(200, json=body)
    return handler


def test_llm_enrichment_rewrites_the_texts(catalog):
    captured = []
    service = ScenarioService(catalog, ScenarioStore(), fake_llm(ok_handler(captured)))
    scenario = service.generate(GenerateRequest(intent="double_billing", language="fr", seed=1, enrich=True))
    assert scenario.enrichment == "llm"
    assert scenario.customer_card.startswith("Vous êtes très en colère")
    assert scenario.sim.problem_type == "double_billing"  # the contract part is untouched
    request = captured[0]
    assert request.headers["Authorization"] == "Bearer test-key"
    assert str(request.url) == "https://example.test/api/v1/chat/completions"
    sent = json.loads(request.content)
    assert sent["model"] == "test/model" and sent["messages"][0]["role"] == "system"


def test_llm_without_key_falls_back_to_templates(catalog):
    service = ScenarioService(catalog, ScenarioStore(), fake_llm(ok_handler(), key=None))
    scenario = service.generate(GenerateRequest(seed=1, enrich=True))
    assert scenario.enrichment == "template" and any("skipped" in n for n in scenario.notes)


def test_no_llm_object_falls_back_to_templates(service):
    scenario = service.generate(GenerateRequest(seed=1, enrich=True))
    assert scenario.enrichment == "template" and scenario.notes


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, json={"error": "boom"}),
        lambda r: httpx.Response(401, json={"error": "bad key"}),
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "not json at all"}}]}),
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": '{"customer_card": "x"}'}}]}),
        lambda r: httpx.Response(200, json={"unexpected": True}),
    ],
)
def test_llm_failures_fall_back_to_templates(catalog, handler):
    service = ScenarioService(catalog, ScenarioStore(), fake_llm(handler))
    scenario = service.generate(GenerateRequest(intent="line_cut", language="en", seed=1, enrich=True))
    assert scenario.enrichment == "template"
    assert scenario.customer_card.startswith("Your line was cut")
    assert any("failed" in n for n in scenario.notes)


def test_llm_network_error_falls_back(catalog):
    def boom(request):
        raise httpx.ConnectError("no network")
    service = ScenarioService(catalog, ScenarioStore(), fake_llm(boom))
    assert service.generate(GenerateRequest(seed=1, enrich=True)).enrichment == "template"


def test_json_parsing_helpers():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! {"a": 1} Hope it helps') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json_object("[1, 2]")
    assert clean_text("hello\x00 world\x07", 100) == "hello world"
    assert clean_text(None, 10) == "" and clean_text("abcdef", 3) == "abc"


# ----------------------------------------------------------------------------- HTTP API
@pytest.fixture
def client(service):
    from main import app
    from scenario_gen.router import get_service

    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_api_health_and_catalog(client):
    assert client.get("/health").json() == {"status": "ok"}
    health = client.get("/scenario-gen/health").json()
    assert health["status"] == "ok" and health["intents"] >= 12
    catalog = client.get("/scenario-gen/catalog").json()
    assert catalog["llm_available"] is False and len(catalog["events"]) >= 10


def test_api_generate_empty_body_and_explicit(client):
    assert client.post("/scenario-gen/scenarios/generate").status_code == 200
    r = client.post("/scenario-gen/scenarios/generate", json={"intent": "line_cut", "difficulty": 4, "seed": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["sim"]["problem_type"] == "line_cut" and body["sim"]["difficulty"] == 4


def test_api_validation_errors(client):
    assert client.post("/scenario-gen/scenarios/generate", json={"difficulty": 9}).status_code == 422
    r = client.post("/scenario-gen/scenarios/generate", json={"intent": "nope"})
    assert r.status_code == 422 and "unknown intent" in r.json()["detail"]
    assert client.get("/scenario-gen/scenarios/sc_missing").status_code == 404
    assert client.post("/scenario-gen/scenarios/sc_missing/replay").status_code == 404


def test_api_full_flow_generate_sim_replay_mutate_lineage(client):
    s = client.post("/scenario-gen/scenarios/generate", json={"seed": 11, "difficulty": 2}).json()
    training = client.get("/training/scenarios")
    assert training.status_code == 200
    assert training.json() == [{
        "id": s["id"],
        "title": s["title"],
        "profile": "New",
        "difficulty": "Easy",
        "origin": "Template library",
    }]
    sim = client.get(f"/scenario-gen/scenarios/{s['id']}/sim").json()
    assert sim == s["sim"] and set(sim) == {"problem_type", "difficulty", "persona_id", "language", "gender", "max_turns", "seed"}
    assert client.post(f"/scenario-gen/scenarios/{s['id']}/replay").json() == s
    m = client.post(f"/scenario-gen/scenarios/{s['id']}/mutate", json={"ops": [{"op": "harder"}]}).json()
    assert m["parent_id"] == s["id"] and m["sim"]["difficulty"] == 3
    bad = client.post(f"/scenario-gen/scenarios/{s['id']}/mutate", json={"ops": [{"op": "set_language", "value": "xx"}]})
    assert bad.status_code == 422
    empty = client.post(f"/scenario-gen/scenarios/{s['id']}/mutate", json={})
    assert empty.status_code == 422
    chain = client.get(f"/scenario-gen/scenarios/{m['id']}/lineage").json()
    assert [x["id"] for x in chain] == [s["id"], m["id"]]
    listed = client.get("/scenario-gen/scenarios", params={"kind": "mutation"}).json()
    assert [x["id"] for x in listed] == [m["id"]]


def test_api_batch_ramp_plan_progress(client):
    batch = client.post("/scenario-gen/scenarios/batch", json={"count": 5, "seed": 1}).json()
    assert len(batch) == 5
    ramp = client.post("/scenario-gen/scenarios/ramp", json={"intent": "line_cut", "seed": 1}).json()
    assert [s["sim"]["difficulty"] for s in ramp] == [1, 2, 3, 4, 5]
    plan = client.post(
        "/scenario-gen/training-plan",
        json={"advisor_id": "a1", "weaknesses": [{"criterion": "Sentiment", "score": 35}], "size": 3, "seed": 2},
    ).json()
    assert plan["needs_training"] and len(plan["scenarios"]) == 3
    assert client.post("/scenario-gen/training-plan", json={"advisor_id": "a1", "weaknesses": []}).status_code == 422
    progress = client.post(
        "/scenario-gen/progress",
        json={"before": [{"criterion": "Sentiment", "score": 35}], "after": [{"criterion": "Sentiment", "score": 70}]},
    ).json()
    assert progress["improved"] == 1


def test_openapi_documents_every_endpoint(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/scenario-gen/scenarios/generate", "/scenario-gen/scenarios/{scenario_id}/mutate", "/scenario-gen/training-plan", "/training/scenarios"):
        assert p in paths
