"""Practice calls: the scenario's words reach the phone, and the result comes back to the coach without touching the quality averages."""
import pytest
from fastapi.testclient import TestClient

import customer
import main
from quality_analyst import store as quality_store
from scenario_gen import practice
from scenario_gen.openings import OPENINGS
from scenario_gen.schemas import GenerateRequest
from scenario_gen.service import ScenarioService
from scenario_gen.store import ScenarioStore


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_DB", str(tmp_path / "quality.db"))
    monkeypatch.setenv("TRAINING_DB", str(tmp_path / "training.db"))
    service = ScenarioService(store=ScenarioStore())
    main.app.dependency_overrides[main.get_service] = lambda: service
    yield TestClient(main.app), service
    main.app.dependency_overrides.clear()


def _played(texts, opening="I lost my phone with my SIM card."):
    s = customer.start("IMPATIENT", None, "MEDIUM", "BILLING", False, opening, "my lost SIM")
    for t in texts:
        customer.say(s["id"], t)
    return s["id"]


GOOD = ["Hello, thank you for calling. I'm sorry about this, can you confirm your date of birth to verify your identity?", "Let me check the policy first.",
        "I can order a replacement SIM that keeps your number and block the old one.", "I will send you a written confirmation by email with a reference number. Is there anything else I can help you with?"]


def test_every_problem_in_the_catalogue_has_words_for_the_phone(catalog):
    assert set(OPENINGS) == set(catalog.intents)
    assert all(line and topic for line, topic in OPENINGS.values())


def test_a_scenario_carries_its_opening_and_the_customer_says_it(catalog):
    scenario = ScenarioService(catalog).generate(GenerateRequest(intent="lost_sim_or_phone", language="en", seed=1))
    assert scenario.opening_line.startswith("I lost my phone") and scenario.call_topic == "my lost SIM"
    s = customer.start("IMPATIENT", None, "MEDIUM", "BILLING", True, scenario.opening_line, scenario.call_topic)
    assert s["opening"].startswith("I lost my phone") and s["opening"].endswith("third time I call about it.")
    answered = customer.say(s["id"], "Hello")
    assert "my bill" not in answered["client"], "the customer's problem is the scenario's, not the simulator's nearest reason"
    assert customer.transcript(s["id"])[0][0]["text"] == s["opening"]


def test_without_a_scenario_the_simulator_is_unchanged():
    s = customer.start("IMPATIENT", None, "MEDIUM", "BILLING", False)
    assert s["opening"] == customer.INTENTS["BILLING"]


def test_a_practice_call_is_reviewed_compared_and_kept_for_the_coach(api):
    client, service = api
    quality_store.ensure_history()
    scenario = service.generate(GenerateRequest(intent="lost_sim_or_phone", language="en", seed=2, advisor_id="Rania K."))
    before = next(a for a in quality_store.analytics()["advisors"] if a["advisor"] == "Rania K.")
    r = client.post("/training/practice", json={"callId": _played(GOOD), "scenario_id": scenario.id, "advisor": "Rim"}).json()
    assert r["advisor"] == "Rania K." and r["source"] == "practice", "the attempt belongs to the scenario's owner"
    p = r["practice"]
    assert p["scenarioId"] == scenario.id and p["overall"] == r["overall"] and p["changes"] and p["next"] in ("harder", "replay")

    after = next(a for a in quality_store.analytics()["advisors"] if a["advisor"] == "Rania K.")
    assert (after["calls"], after["avgOverall"]) == (before["calls"], before["avgOverall"]), "practice does not change the quality averages"
    history = client.get("/training/practice", params={"advisor": "Rania K."}).json()
    assert history["count"] == 1 and history["best"] == r["overall"] and history["attempts"][0]["callId"] == r["callId"] and history["trend"] is None


def test_the_trend_runs_from_the_first_attempt_to_the_latest(api):
    client, service = api
    scenario = service.generate(GenerateRequest(intent="double_billing", language="en", seed=3, advisor_id="Sami R."))
    bad = client.post("/training/practice", json={"callId": _played(["Could you explain the problem again from the start?"]), "scenario_id": scenario.id, "advisor": "x"}).json()
    good = client.post("/training/practice", json={"callId": _played(GOOD), "scenario_id": scenario.id, "advisor": "x"}).json()
    history = client.get("/training/practice", params={"advisor": "Sami R."}).json()
    assert history["count"] == 2 and history["trend"] == good["overall"] - bad["overall"] > 0
    assert bad["practice"]["next"] == "replay"


def test_practice_refuses_unknown_calls_scenarios_and_silent_calls(api):
    client, service = api
    scenario = service.generate(GenerateRequest(language="en", seed=4))
    assert client.post("/training/practice", json={"callId": "0" * 16, "scenario_id": scenario.id, "advisor": "x"}).status_code == 404
    assert client.post("/training/practice", json={"callId": _played(GOOD), "scenario_id": "sc_nope", "advisor": "x"}).status_code == 404
    assert client.post("/training/practice", json={"callId": _played([]), "scenario_id": scenario.id, "advisor": "x"}).status_code == 400


def test_the_advice_follows_the_score_and_what_got_worse():
    worse = [dict(criterion="Compliance", status="regressed")]
    assert practice.advice(92, [], "Accuracy")[0] == "harder"
    assert practice.advice(92, worse, "Accuracy")[0] == "replay" and "compliance" in practice.advice(92, worse, "Accuracy")[1]
    assert "Nearly" in practice.advice(70, [], "Compliance")[1]
    assert "go through the review" in practice.advice(40, [], "Compliance")[1]


def test_the_advisor_agent_s_own_call_does_not_count_either(api):
    client, _ = api
    quality_store.ensure_history()
    before = quality_store.analytics()["team"]["calls"]
    r = client.post("/quality/review-call", json={"callId": _played(GOOD), "advisor": "Advisor agent", "source": "automatic"}).json()
    assert r["source"] == "automatic" and quality_store.get(r["callId"])
    assert quality_store.analytics()["team"]["calls"] == before


def test_a_reader_that_shows_no_explanation_does_not_pay_for_it(api):
    quality_store.ensure_history()
    assert all("drivers" not in r for r in quality_store.recent(limit=200, with_drivers=False))
    assert all("drivers" in r for r in quality_store.recent(limit=3))
