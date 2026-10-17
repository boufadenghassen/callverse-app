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


def test_voice_notes_are_written_down_or_refused():
    import io

    import numpy as np
    import soundfile as sf
    import stt
    if not (stt.available() and voice.available()):
        pytest.skip("voice models not downloaded")
    wav = voice.speak("I will check the refund policy first.", "advisor")
    r = client.post("/voice/transcribe", content=wav, headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200 and "refund policy" in r.json()["text"].lower()
    silent = io.BytesIO()
    sf.write(silent, np.zeros(16000, dtype="float32"), 16000, format="WAV")
    assert client.post("/voice/transcribe", content=silent.getvalue()).status_code == 400
    assert client.post("/voice/transcribe", content=b"not audio at all").status_code == 400
    assert client.post("/voice/transcribe", content=b"").status_code == 400


import workforce  # noqa: E402


def test_erlang_c_matches_the_textbook_and_behaves():
    assert round(workforce.erlang_c(11, 10), 4) == 0.6821                      # classic example: 11 advisors, 10 erlangs
    assert workforce.erlang_c(5, 5) == 1.0 and workforce.erlang_c(3, 7) == 1.0   # no spare capacity: everybody waits
    waits = [workforce.stats(72, 300, n)["wait"] for n in range(7, 14)]
    slas = [workforce.stats(72, 300, n)["sla"] for n in range(7, 14)]
    assert waits == sorted(waits, reverse=True) and slas == sorted(slas)         # more advisors: shorter wait, better service level
    assert workforce.stats(72, 300, 6)["wait"] == workforce.WAIT_CAP             # 6 erlangs of load with 6 advisors: overloaded
    assert workforce.stats(0, 300, 3)["sla"] == 1.0
    n = workforce.advisors_needed(72, 300)
    assert workforce.stats(72, 300, n)["sla"] >= 0.8 > workforce.stats(72, 300, n - 1)["sla"]


def test_the_forecast_has_one_point_per_hour_and_actuals_only_until_now():
    for q in "ABCDE":
        f = workforce.forecast(q)
        assert [p["hour"] for p in f] == [f"{h}h" for h in range(9, 18)]
        assert all(p["actual"] is not None for p in f[:5]) and all(p["actual"] is None for p in f[5:])
        assert all(isinstance(p["forecast"], int) and p["forecast"] > 0 for p in f)
    assert workforce.forecast("B") == workforce.forecast("B")                     # deterministic


def test_a_simulation_is_consistent_with_the_hour_by_hour_numbers():
    r = workforce.simulate("B", 2, "14:00", "16:00")
    assert [h["hour"] for h in r["hours"]] == ["14h", "15h"]
    assert r["simulatedSla"] > r["baselineSla"] and r["simulatedWaitSec"] < r["baselineWaitSec"]
    calls = [h["calls"] for h in r["hours"]]
    assert abs(r["baselineSla"] - sum(h["baselineSla"] * c for h, c in zip(r["hours"], calls)) / sum(calls)) < 0.011
    assert all(h["simulatedAdvisors"] == h["advisors"] + 2 for h in r["hours"])
    assert any("Add" in t and "queue B" in t for t in r["recommendations"])
    same = workforce.simulate("B", 0, "14:00", "16:00")
    assert (same["baselineWaitSec"], same["baselineSla"]) == (same["simulatedWaitSec"], same["simulatedSla"])
    fewer = workforce.simulate("B", -2, "14:00", "16:00")
    assert fewer["simulatedSla"] < fewer["baselineSla"]
    half = workforce.simulate("B", 1, "14:30", "15:00")                          # half an hour counts as half an hour
    assert [h["hour"] for h in half["hours"]] == ["14h"]


def test_a_window_outside_opening_hours_says_so():
    r = workforce.simulate("A", 3, "19:00", "21:00")
    assert r["hours"] == [] and "No opening hours" in r["recommendations"][0]


def test_the_workforce_endpoints_validate_their_input():
    assert len(client.get("/workforce/forecast", params={"queue": "C"}).json()) == 9
    assert client.get("/workforce/forecast", params={"queue": "Z"}).status_code == 422
    ok = client.post("/workforce/simulate", json={"queue": "B", "extraAdvisors": 2, "from": "14:00", "to": "16:00"})
    assert ok.status_code == 200 and ok.json()["simulatedSla"] > ok.json()["baselineSla"]
    for bad in ({"queue": "B", "extraAdvisors": 99, "from": "14:00", "to": "16:00"}, {"queue": "B", "extraAdvisors": 1, "from": "16:00", "to": "14:00"},
                {"queue": "B", "extraAdvisors": 1, "from": "25:00", "to": "26:00"}, {"queue": "Q", "extraAdvisors": 1, "from": "14:00", "to": "16:00"}):
        assert client.post("/workforce/simulate", json=bad).status_code == 422
