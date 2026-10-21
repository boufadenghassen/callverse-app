"""Awkward input must never crash the analyst: odd texts, odd moods, huge calls, bad filters. Found by a fuzz run (300 random calls) that came out clean."""
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from main import app  # noqa: E402
from quality_analyst import engine  # noqa: E402

NASTY = ["", " ", "?" * 500, "a" * 20000, "ça va ? merci beaucoup, je suis très en colère", "مرحبا كيف يمكنني مساعدتك", "😡😡😡", "<script>alert(1)</script>",
         "I guarantee " * 800, "(" * 3000, "\\" * 500, "1" * 400 + " TND refund", "I will refund 99999999999999999999 TND", "no " * 4000]
client = TestClient(app)


@pytest.mark.parametrize("text", NASTY)
def test_odd_texts_are_scored_without_crashing(text):
    for turns in ([dict(speaker="customer", text="I was charged twice"), dict(speaker="advisor", text=text)],
                  [dict(speaker="customer", text=text), dict(speaker="advisor", text="Hello, how can I help?")]):
        r = engine.review(turns, "Fuzz", "CALL-0001")
        assert 0 <= r["overall"] <= 100


def test_odd_call_shapes():
    for turns in ([dict(speaker="customer", text="hi")] * 3, [dict(speaker="advisor", text="hello")] * 3,
                  [dict(speaker="customer", text="hi", mood=500), dict(speaker="advisor", text="hello")],
                  [dict(speaker="customer", text="hi", start=50, end=10), dict(speaker="advisor", text="hello", start=5, end=2)]):
        assert 0 <= engine.review(turns, "Fuzz", "CALL-0002")["overall"] <= 100


def test_a_long_call_is_fast():
    turns = [dict(speaker="advisor" if i % 2 else "customer", text="I will check the policy and refund you, please wait " * 5) for i in range(200)]
    engine.review(turns[:2], "Fuzz", "CALL-0003")      # loads the embedding model when it is there
    start = time.time()
    engine.review(turns, "Fuzz", "CALL-0004")
    assert time.time() - start < 5


@pytest.mark.parametrize("query", ["limit=0", "limit=-1", "limit=abc", "advisor=" + "x" * 5000, "rule=' or 1=1 --", "below=abc", "below=-5", "advisor=%00"])
def test_bad_filters_never_give_a_server_error(query):
    assert client.get("/quality/reviews?" + query).status_code < 500


@pytest.mark.parametrize("body", [{}, {"advisor": "x", "turns": []}, {"advisor": "x", "turns": [{"speaker": "robot", "text": "hi"}]},
                                  {"advisor": "x", "turns": [{"speaker": "advisor", "text": "hi", "mood": 101}]},
                                  {"advisor": "x", "turns": [{"speaker": "advisor", "text": "a" * 1001}]}])
def test_bad_transcripts_are_refused_with_a_client_error(body):
    assert 400 <= client.post("/quality/review", json=body).status_code < 500
