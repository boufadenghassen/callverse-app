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


import pytest  # noqa: E402
import voice  # noqa: E402


def test_voice_speed_follows_mood_and_voices_follow_persona():
    assert voice.speed_for(0) == 1.2 and voice.speed_for(100) == 0.85 and voice.speed_for(50) == 1.0
    assert voice.voice_for("advisor", "ANGRY_PREMIUM") == voice.ADVISOR_VOICE
    assert voice.voice_for("customer", "ANGRY_PREMIUM") != voice.voice_for("customer", "ANXIOUS")
    assert voice.voice_for("customer", None) == voice.DEFAULT_CUSTOMER_VOICE


def test_the_voice_endpoint_returns_audio_or_says_it_is_missing():
    r = client.post("/voice/speak", json={"text": "Hello there.", "role": "customer", "persona": "ANXIOUS", "mood": 30})
    if not voice.available():
        assert r.status_code == 503
        pytest.skip("voice model files not downloaded")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"
    assert client.post("/voice/speak", json={"text": "", "role": "advisor"}).status_code == 422
    assert client.post("/voice/speak", json={"text": "x" * 401}).status_code == 422
    assert client.post("/voice/speak", json={"text": "hi", "mood": 101}).status_code == 422
