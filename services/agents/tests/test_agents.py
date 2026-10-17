"""Run from services/agents:  ../../../venv/Scripts/python.exe -m pytest -q"""
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import advisor  # noqa: E402
import customer  # noqa: E402
from main import app  # noqa: E402

GOLD = json.loads((Path(__file__).parent / "golden_customer.json").read_text(encoding="utf-8"))
client = TestClient(app)


def test_reading_the_advisor_matches_the_typescript_version():
    for text, move in GOLD["texts"]:
        assert customer.read_advisor(text) == move, text


def test_customer_calls_replay_exactly_like_the_typescript_version():
    for c in GOLD["cases"]:
        r = customer.replay(c["persona"], c["mix"], c["difficulty"], c["intent"], c["memory"], c["moves"], c["said"])
        assert r.opening == c["opening"]
        got = [(t.move, t.client, t.mood, t.patience) for t in r.turns]
        want = [(t["move"], t["client"], t["mood"], t["patience"]) for t in c["turns"]]
        assert got == want, c["persona"]
        assert (r.outcome or None) == (c["outcome"] or None)


def test_a_live_call_over_http():
    s = client.post("/customer/sessions", json={"persona": "ANGRY_PREMIUM", "difficulty": "HARD", "intent": "BILLING"}).json()
    assert s["opening"].startswith("I was charged twice") and s["mood"] == 35
    a = client.post(f"/customer/sessions/{s['id']}/say", json={"text": "I'm so sorry, I understand how frustrating this is."}).json()
    assert a["move"] == "EMPATHY" and a["mood"] > 35 and a["client"]
    b = client.post(f"/customer/sessions/{s['id']}/say", json={"text": "I promise the refund right away."}).json()
    assert b["move"] == "PROMISE"
    done = client.post(f"/customer/sessions/{s['id']}/say", json={"text": "I will send you a confirmation by email."}).json()
    assert done["ended"] and done["outcome"]["churnRisk"] >= 0
    assert client.post(f"/customer/sessions/{s['id']}/say", json={"text": "hello"}).json()["ended"] is True


def test_bad_input_is_refused():
    assert client.post("/customer/sessions", json={"persona": "NOPE"}).status_code == 422
    assert client.post("/customer/sessions/0123456789abcdef/say", json={"text": "hi"}).status_code == 404
    assert client.post("/customer/sessions/not-an-id/say", json={"text": "hi"}).status_code == 404
    assert client.post("/advisor/suggest", json={"customer_id": "bad", "query": "double charge"}).status_code == 422


def test_the_advisor_answers_from_the_right_passage_and_cites_it():
    cases = {
        "I was charged twice on my September bill": "Billing policy §4.2",
        "my roaming bundle did not work abroad": "Roaming guide §2",
        "I want to cancel and this early termination fee makes no sense": "Contract terms §7",
        "my mobile data finished too early": "Data usage FAQ §3",
    }
    for query, source in cases.items():
        a = advisor.suggest(query)
        assert a["sources"][0] == source, (query, a["sources"])
        assert a["evidence"][0]["score"] == a["confidence"] > 0.08


def test_the_advisor_flags_big_refunds_and_admits_when_it_does_not_know():
    assert "supervisor" in advisor.suggest("I was charged twice, please refund 120 TND")["policyWarning"]
    unknown = advisor.suggest("what is the weather on mars")
    assert unknown["sources"] == [] and "could not find" in unknown["text"]


def test_intents_come_out_as_chips():
    assert {"Billing", "Roaming"} <= set(advisor.detect_intents("charged twice for my roaming bundle"))
