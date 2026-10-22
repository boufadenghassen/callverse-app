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


def test_the_advisor_looks_up_a_known_customer_and_refuses_an_unknown_one():
    r = client.get("/advisor/customers/YT-1042")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "YT-1042" and body["name"] == "Yasmine Toumi" and body["mood"]
    assert client.get("/advisor/customers/ZZ-0000").status_code == 404
    assert client.get("/advisor/customers/not-an-id").status_code == 422


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


import routing  # noqa: E402


def test_routing_keeps_every_advisor_and_respects_skills_and_the_protected_level():
    for h in workforce.HOURS:
        if h <= workforce.NOW_HOUR:
            continue
        plan = routing.allocate(h)
        before = sum(q["advisors"] for q in plan["queues"])
        assert before == sum(q["recommended"] for q in plan["queues"]) == len(routing.on_duty(h))     # nobody appears or disappears
        skills = {a["id"]: a["skills"] for a in routing.advisors()}
        for m in plan["moves"]:
            assert m["toQueue"] in skills[m["advisor"]] and m["fromQueue"] != m["toQueue"]
            assert m["gain"] > 0
        for q in plan["queues"]:                                  # a donor never ends below the protected level (or below where it started)
            if q["recommended"] < q["advisors"]:
                assert q["recommendedSla"] >= min(routing.GUARD, q["baselineSla"]) - 0.011


def test_routing_never_makes_the_weighted_service_level_worse():
    for h in (14, 15, 16, 17):
        plan = routing.allocate(h)
        calls = {q["queue"]: q["calls"] for q in plan["queues"]}
        before = routing.objective(calls, {q["queue"]: q["advisors"] for q in plan["queues"]})
        after = routing.objective(calls, {q["queue"]: q["recommended"] for q in plan["queues"]})
        assert after >= before - 1e-9


def test_the_plan_gains_service_level_and_an_independent_simulation_agrees():
    p = routing.plan()
    assert p["moves"] >= 1 and p["optimizedSla"] > p["baselineSla"]
    assert p["simulated"]["optimizedSla"] > p["simulated"]["baselineSla"]
    assert abs(p["simulated"]["baselineSla"] - p["baselineSla"]) < 0.06           # the formula and the simulation tell the same story
    assert routing.plan() is routing.plan()                                       # deterministic and cached


def test_the_simulation_matches_erlang_c():
    for calls, aht, n in ((72, 300, 8), (40, 420, 7), (20, 200, 3)):
        formula = workforce.stats(calls, aht, n)["sla"]
        assert abs(routing.simulate_hour(calls, aht, n, reps=150, seed=7) - formula) < 0.05, (calls, aht, n)
    assert routing.simulate_hour(0, 300, 3, 5, 1) == 1.0 and routing.simulate_hour(50, 300, 0, 5, 1) == 0.0


def test_the_routing_endpoint():
    r = client.get("/workforce/routing")
    assert r.status_code == 200
    body = r.json()
    assert [h["hour"] for h in body["hours"]] == ["14h", "15h", "16h", "17h"] and "method" in body
    assert all(set(q) >= {"queue", "advisors", "recommended", "baselineSla", "recommendedSla"} for q in body["hours"][0]["queues"])


import scheduling  # noqa: E402


def test_every_eligible_advisor_gets_exactly_one_lunch_inside_the_shift():
    for q in "ABCDE":
        pq = scheduling.plan_queue(q)
        lunch = pq["_lunch"]
        shifts = scheduling.shifts(q)
        assert set(lunch) == {i for i, s in enumerate(shifts) if len(s) >= scheduling.MIN_SHIFT_HOURS and any(h in s for h in scheduling.LUNCH_HOURS)}
        assert all(h in scheduling.LUNCH_HOURS and h in shifts[i] for i, h in lunch.items())     # inside the lunch window and the advisor's own shift
        assert sum(x["planned"] for x in pq["lunchHours"]) == sum(x["naive"] for x in pq["lunchHours"]) == len(lunch)
        for x in pq["lunchHours"]:
            assert x["planned"] <= x["onDuty"]


def test_the_planned_lunches_beat_everybody_at_noon():
    p = scheduling.plan()
    assert p["plannedSla"] >= p["baselineSla"]
    for q in p["queues"]:
        assert q["plannedSla"] >= q["baselineSla"] - 1e-9, q["queue"]
        assert q["worstPlanned"]["sla"] >= q["worstBaseline"]["sla"], q["queue"]                # the worst hour is never worse than with everybody at noon
    assert max(x["naive"] for q in p["queues"] for x in q["lunchHours"]) > max(x["planned"] for q in p["queues"] for x in q["lunchHours"])   # noon is no longer a stampede
    assert all(o["advisors"] >= 1 and o["sla"] < 0.8 for o in p["overtime"])
    assert scheduling.plan() is scheduling.plan()


def test_the_schedule_endpoint():
    r = client.get("/workforce/schedule")
    assert r.status_code == 200
    body = r.json()
    assert {"baselineSla", "plannedSla", "queues", "overtime", "overtimeHours", "method"} <= set(body)
    assert len(body["queues"]) == 5 and all("_lunch" not in q for q in body["queues"])


def test_she_hears_a_raised_voice_rude_words_and_shouting():
    angry, calm = {"emotion": "anger", "mood": 14}, {"emotion": "happy", "mood": 85}
    assert customer.read_advisor("I am sorry about that.", angry) == "RUDE"        # polite words, angry voice
    assert customer.read_advisor("I am sorry about that.", calm) == "EMPATHY"
    assert customer.read_advisor("I am sorry about that.", {"emotion": "anger", "mood": 60}) == "EMPATHY"   # a weak reading is not enough
    assert customer.read_advisor("I am sorry about that.", {"emotion": "sad", "mood": 5}) == "EMPATHY"      # only anger or disgust counts
    assert customer.read_advisor("Don't be stupid.") == "RUDE" and customer.read_advisor("shut up and listen") == "RUDE"
    assert customer.read_advisor("I WANT MY MONEY BACK NOW") == "RUDE" and customer.read_advisor("What are you doing!!!") == "RUDE"
    assert customer.read_advisor("Please send the SMS and USB details.") == "OTHER"                       # acronyms are not shouting


def test_a_raised_voice_costs_patience_ends_the_call_badly_and_is_noted():
    kw = dict(persona="IMPATIENT", mix=None, difficulty="MEDIUM", intent="BILLING", memory=False)
    calm = customer.replay(**kw, moves=["EMPATHY"], said=["I am sorry."])
    rude = customer.replay(**kw, moves=["RUDE"], said=["I am sorry."])
    assert rude.mood < calm.mood - 15 and rude.patience < calm.patience - 15
    done = customer.replay(**kw, moves=["RUDE", "EMPATHY", "CHECK_POLICY", "FOLLOW_UP"], said=[None] * 4)
    assert done.outcome and done.outcome["expectationMet"] is False and any("Conduct" in n for n in done.outcome["notes"])
    assert customer.replay(**kw, moves=["RUDE", "RUDE", "RUDE"], said=[None] * 3).outcome["verdict"] == "The client hung up."


def test_she_answers_what_was_actually_said_when_it_matches_no_move():
    def line(said, mood=50):
        return customer.customer_line("NEW_SUBSCRIBER", "BILLING", "OTHER", mood, False, False, 0, said)
    assert "$2,000" in line("Why did you put $2,000?") and "45 TND" in line("Is this about 45 TND?")
    assert "my bill" in line("Hello, how are you today?") and "my bill" in line("Can you give me your name?")
    assert "my bill" not in line("The weather is nice today.") and "my bill" not in line(None)
    assert line("Why did you put $2,000?") == line("Why did you put $2,000?")                                        # same words, same answer
    assert line("Why did you put $2,000?", 10) != line("Why did you put $2,000?", 90)                                # and her mood shapes it


def test_the_tone_of_a_voice_note_reaches_her_over_http():
    kw = {"persona": "IMPATIENT", "difficulty": "MEDIUM", "intent": "BILLING"}

    def say(sid, body):
        return client.post(f"/customer/sessions/{sid}/say", json=body).json()

    a, b = client.post("/customer/sessions", json=kw).json(), client.post("/customer/sessions", json=kw).json()
    calm = say(a["id"], {"text": "I am sorry about that."})
    shouted = say(b["id"], {"text": "I am sorry about that.", "tone": {"emotion": "anger", "mood": 12}})
    assert calm["move"] == "EMPATHY" and shouted["move"] == "RUDE" and shouted["moveLabel"] == "Raised your voice or was rude"
    assert shouted["mood"] < calm["mood"] and shouted["client"] != calm["client"]
    for bad in ({"emotion": "furious", "mood": 10}, {"emotion": "anger", "mood": 101}, {"emotion": "anger"}):
        assert client.post(f"/customer/sessions/{a['id']}/say", json={"text": "hi", "tone": bad}).status_code == 422

