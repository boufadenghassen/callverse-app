"""Quality analyst tests. Run from services/agents:  ../../../venv/Scripts/python.exe -m pytest -q tests/test_quality.py"""
import datetime as dt
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customer  # noqa: E402
import quality  # noqa: E402
import quality_seed  # noqa: E402
import quality_store  # noqa: E402
import stt  # noqa: E402
import voice  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def own_store(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_DB", str(tmp_path / "quality.db"))


def T(speaker, start, text, mood=None):
    return dict(speaker=speaker, start=start, text=text, mood=mood)


GOOD = [
    T("customer", 0, "I was charged twice on my September bill.", 45),
    T("advisor", 8, "Hello, thank you for calling. I am sorry about that, I understand how frustrating a double charge is. Can you confirm your date of birth so I can verify your identity?"),
    T("customer", 30, "Sure, it is the third of May 1990.", 50),
    T("advisor", 38, "Thank you. I can see the amount was charged twice. Let me check the refund policy and the approval first. The refund appears on the next statement, and I will send you "
                     "a confirmation by email with a reference number. Is there anything else I can help with?"),
    T("customer", 75, "Thank you, that is great.", 80),
]
BAD = [
    T("customer", 0, "I was charged twice on my September bill, this is the third time I call about it.", 28),
    T("advisor", 9, "Yes. Let me see the account."),
    T("customer", 24, "Again?! I already told your colleagues everything!", 22),
    T("advisor", 35, "I will refund you right away, 120 TND, I guarantee it will not happen again. Your APN is fine."),
    T("customer", 60, "Okay... but I have heard that before.", 34),
    T("advisor", 72, "Please hold while I transfer you to the billing team."),
    T("customer", 90, "Another transfer? Unbelievable. I am hanging up.", 15),
]


def rules(r):
    return {e["rule"] for e in r["errors"]}


def test_a_good_call_scores_full_marks_and_shows_its_strengths():
    r = quality.review(GOOD, "A.", "CALL-1")
    assert r["overall"] == 100 and r["errors"] == [] and all(c["score"] == 10 for c in r["criteria"])
    assert {"empathy", "identity", "greeting", "follow_up", "closing", "check_first", "mood_up"} <= {s["rule"] for s in r["strengths"]}


def test_a_bad_call_loses_points_for_the_right_reasons_at_the_right_moments():
    r = quality.review(BAD, "B.", "CALL-2")
    assert {"promise_before_check", "refund_over_limit", "no_identity_check", "overpromise", "jargon", "no_empathy", "transfer", "no_follow_up",
            "no_greeting", "no_closing", "hang_up", "mood_drop", "unresolved"} <= rules(r)
    promise = next(e for e in r["errors"] if e["rule"] == "promise_before_check")
    assert promise["timestamp"] == "00:35" and "120 TND" in promise["quote"] and promise["criterion"] == "Compliance"
    comp = next(c for c in r["criteria"] if c["name"] == "Compliance")
    assert comp["score"] == 0 and comp["timestamp"] == "00:35" and "Promised a refund" in comp["evidence"]
    assert r["overall"] < 30 and [c["name"] for c in r["criteria"]] == quality.CRITERIA
    flagged = {i for i, t in enumerate(r["turns"]) if t["flags"]}
    assert 3 in flagged and 5 in flagged                         # the promise turn and the transfer turn are marked in the transcript


def test_each_rule_fires_only_when_it_should():
    def has(turns, rule):
        return rule in rules(quality.review(turns, "X.", "C"))

    base = [T("customer", 0, "I was charged twice on my bill.", 55), T("advisor", 5, "Hello. I understand, I am sorry. Let me check the refund policy first.")]
    assert not has(base, "promise_before_check")
    assert has(base[:1] + [T("advisor", 5, "Hello. I will refund you right away.")], "promise_before_check")
    assert not has(base + [T("customer", 20, "ok", 55), T("advisor", 25, "I will refund you the amount now.")], "promise_before_check")          # the check came first
    assert has(base[:1] + [T("advisor", 5, "Hello. I will refund you 90 TND.")], "refund_over_limit")
    assert not has(base[:1] + [T("advisor", 5, "Hello. I will refund 90 TND once my supervisor has approved it.")], "refund_over_limit")
    assert not has(base[:1] + [T("advisor", 5, "Hello. I will refund you 30 TND.")], "refund_over_limit")                                           # under the limit
    assert has(base[:1] + [T("advisor", 5, "Hello. The dispute will be answered within two days.")], "wrong_fact")
    assert not has(base[:1] + [T("advisor", 5, "Hello. The dispute will be answered within five working days.")], "wrong_fact")
    assert has(base[:1] + [T("advisor", 5, "Hello. A plan change takes effect immediately.")], "wrong_fact")
    assert has([T("customer", 0, "I am furious, this is unacceptable.", 20), T("advisor", 6, "Hello. Let me look at the bill.")], "no_empathy")
    assert not has([T("customer", 0, "I am furious, this is unacceptable.", 20), T("advisor", 6, "Hello. I am sorry, I understand your frustration.")], "no_empathy")
    assert not has(base, "no_empathy")                                                                                                                # customer was calm


def test_the_counterfactual_is_exact():
    r = quality.review(BAD, "B.", "CALL-2")
    issues, _ = quality.find_issues(*[quality.normalize(BAD)[0]], intent_text=BAD[0]["text"], outcome=None)
    scores = quality.score(issues)
    best = max(issues, key=lambda f: quality.overall(quality.score([x for x in issues if x is not f])))
    gain = quality.overall(quality.score([x for x in issues if x is not best])) - quality.overall(scores)
    assert f"overall score by +{gain}" in r["counterfactual"] and best["timestamp"] in r["counterfactual"]


def test_missing_times_and_moods_are_filled_in_and_the_source_is_said():
    r = quality.review([dict(speaker="customer", text="This is terrible, I am furious, unacceptable."), dict(speaker="advisor", text="Hello, I am sorry.")], "X.", "C")
    assert r["moodSource"] == "text" and r["turns"][0]["mood"] < 45 and r["turns"][1]["start"] > r["turns"][0]["end"] - 1e-9
    assert quality.review(GOOD, "X.", "C")["moodSource"] == "given"


def test_a_call_without_any_advisor_turn_is_a_failure_not_a_crash():
    r = quality.review([T("customer", 0, "Hello? Is anybody there?", 40)], "X.", "C")
    assert r["overall"] < 40 and "unresolved" in rules(r)


def test_the_simulated_history_is_deterministic_and_the_analytics_are_computed_from_it():
    quality_store.ensure_history()
    assert quality_store.count() == 84
    today = dt.date.today()
    a = quality_store.analytics(today)
    assert a["team"]["calls"] == 84 and len(a["advisors"]) == 6 and len(a["team"]["weeks"]) == 8
    by = {x["advisor"]: x for x in a["advisors"]}
    assert by["Sami R."]["trend"] > 5 > -5 > by["Mehdi T."]["trend"]                      # the improving advisor improves, the declining one declines
    assert by["Ines F."]["weakest"]["criterion"] == "Accuracy"                            # warm but wrong on facts
    assert by["Rania K."]["weakest"]["criterion"] == "Compliance"
    assert abs(sum(x["avgOverall"] * x["calls"] for x in a["advisors"]) / 84 - a["team"]["avgOverall"]) < 0.2
    for adv in a["advisors"]:
        assert adv["coaching"] and all(c["tip"] and c["scenario"] and c["calls"] >= 1 for c in adv["coaching"])
    assert {e["rule"] for e in a["team"]["topErrors"]} <= set(quality.RULE_LABELS)
    assert abs(sum(c["share"] for c in a["team"]["causes"]) - 1) < 0.02
    ids = [r["callId"] for r in quality_store.recent(100)]
    assert len(set(ids)) == 84 and quality_store.next_call_id() == f"CALL-{quality_store.FIRST_ID + 84}"
    before = quality_store.count()
    quality_store.ensure_history()
    assert quality_store.count() == before                                                  # not created twice


def test_every_rule_has_a_label_a_tip_a_scenario_and_a_cause():
    for rule, r in quality.RULES.items():
        assert rule in quality.RULE_LABELS and r["tip"] and r["scenario"] and r["cause"] and r["criterion"] in quality.CRITERIA


def test_reviews_over_http_are_saved_and_listed():
    ok = client.post("/quality/review", json={"advisor": "Karim B.", "turns": [{"speaker": t["speaker"], "text": t["text"], "start": t["start"], "mood": t["mood"]} for t in BAD]})
    assert ok.status_code == 200 and ok.json()["callId"] == f"CALL-{quality_store.FIRST_ID}" and ok.json()["source"] == "api"
    listed = client.get("/quality/reviews").json()
    assert [r["callId"] for r in listed] == [ok.json()["callId"]]
    assert client.get(f"/quality/reviews/{ok.json()['callId']}").json()["overall"] == ok.json()["overall"]
    assert client.get("/quality/reviews", params={"advisor": "Nobody"}).json() == []
    assert client.get("/quality/reviews/CALL-9999").status_code == 404
    assert client.get("/quality/reviews/not-an-id").status_code == 422


def test_bad_review_input_is_refused():
    assert client.post("/quality/review", json={"advisor": "", "turns": [{"speaker": "advisor", "text": "hi"}]}).status_code == 422
    assert client.post("/quality/review", json={"advisor": "A.", "turns": []}).status_code == 422
    assert client.post("/quality/review", json={"advisor": "A.", "turns": [{"speaker": "robot", "text": "hi"}]}).status_code == 422
    assert client.post("/quality/review", json={"advisor": "A.", "turns": [{"speaker": "advisor", "text": "x" * 1001}]}).status_code == 422
    assert client.post("/quality/review", json={"advisor": "A.", "turns": [{"speaker": "advisor", "text": "hi", "mood": 101}]}).status_code == 422


def test_a_live_call_can_be_sent_to_quality():
    s = client.post("/customer/sessions", json={"persona": "ANGRY_PREMIUM", "difficulty": "HARD", "intent": "BILLING"}).json()
    assert client.post("/quality/review-call", json={"callId": s["id"], "advisor": "Karim B."}).status_code == 400     # nothing said yet
    client.post(f"/customer/sessions/{s['id']}/say", json={"text": "Hello, I am sorry about that, I understand how frustrating it is."})
    client.post(f"/customer/sessions/{s['id']}/say", json={"text": "I will refund you right away."})
    r = client.post("/quality/review-call", json={"callId": s["id"], "advisor": "Karim B."})
    assert r.status_code == 200 and r.json()["source"] == "live call" and "promise_before_check" in {e["rule"] for e in r.json()["errors"]}
    assert [t["speaker"] for t in r.json()["turns"]] == ["customer", "advisor", "customer", "advisor", "customer"]
    assert client.post("/quality/review-call", json={"callId": "0123456789abcdef", "advisor": "K."}).status_code == 404
    assert client.post("/quality/review-call", json={"callId": "nope", "advisor": "K."}).status_code == 422


def test_the_analytics_endpoint():
    assert client.get("/quality/analytics").json()["team"] is None                  # an empty store: nothing to average
    quality_store.ensure_history()
    body = client.get("/quality/analytics").json()
    assert body["team"]["calls"] == 84 and body["advisors"][0]["avgOverall"] <= body["advisors"][-1]["avgOverall"]


needs_models = pytest.mark.skipif(not (stt.available() and voice.available()), reason="voice models not downloaded")


@needs_models
def test_a_two_channel_recording_is_transcribed_by_speaker_and_scored():
    import quality_audio
    wav = quality_audio.sample_call()
    turns = quality_audio.transcript(wav)
    assert {t["speaker"] for t in turns} == {"advisor", "customer"}
    assert "charged twice" in " ".join(t["text"].lower() for t in turns if t["speaker"] == "customer")
    r = client.post("/quality/review-audio", params={"advisor": "Karim B."}, content=wav, headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200 and r.json()["source"] == "recording"
    assert {"ask_repeat", "transfer", "no_greeting"} <= {e["rule"] for e in r.json()["errors"]}
    assert client.get("/quality/sample-call.wav").content[:4] == b"RIFF"


@needs_models
def test_recordings_that_cannot_be_reviewed_are_refused_kindly():
    import io

    import numpy as np
    import soundfile as sf
    mono = io.BytesIO()
    sf.write(mono, np.zeros(16000, dtype="float32") + 0.1, 16000, format="WAV")
    assert client.post("/quality/review-audio", content=mono.getvalue(), headers={"Content-Type": "audio/wav"}).status_code == 422
    assert client.post("/quality/review-audio", content=b"not audio", headers={"Content-Type": "audio/wav"}).status_code == 400
    silent = io.BytesIO()
    sf.write(silent, np.zeros((16000, 2), dtype="float32"), 16000, format="WAV")
    assert client.post("/quality/review-audio", content=silent.getvalue(), headers={"Content-Type": "audio/wav"}).status_code == 400
    assert client.post("/quality/review-audio", content=b"").status_code == 400
