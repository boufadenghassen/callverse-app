"""The advisor's trained intent model is an optional extra on top of the rules: it changes an answer only when its files are there, and says so."""
import datetime as dt
import os

import pytest

import advisor
import intent_model
from complaints_agent import engine


def _fake(intent, confidence=0.95):
    return lambda text: dict(intent=intent, label=intent.replace("_", " "), category="BILLING", chip="Billing", confidence=confidence,
                             sure=confidence >= intent_model.MIN_CONFIDENCE, alternatives=[], passages=intent_model.PASSAGES.get(intent, []))


def test_the_intent_model_finds_the_passage_that_tfidf_misses(monkeypatch):
    monkeypatch.setattr(intent_model, "predict", _fake("dispute_invoice"))
    answer = advisor.suggest("the amount on my statement is wrong and I don't agree with it")
    assert answer["evidence"][0]["excerpt"] in intent_model.PASSAGES["dispute_invoice"]
    assert answer["intentModel"]["intent"] == "dispute_invoice" and "Billing" in answer["intents"]


def test_an_unsure_intent_model_changes_nothing(monkeypatch):
    query = "the amount on my statement is wrong and I don't agree with it"
    before = advisor.suggest(query)
    monkeypatch.setattr(intent_model, "predict", _fake("cancel_plan", confidence=0.3))
    assert advisor.suggest(query)["evidence"] == before["evidence"]


def test_an_intent_with_no_passage_is_named_and_escalated_instead_of_guessed(monkeypatch):
    monkeypatch.setattr(intent_model, "predict", _fake("install_internet", confidence=0.9))
    answer = advisor.suggest("zzz qqq")
    assert answer["sources"] == [] and "install internet" in answer["text"]


def test_without_the_intent_model_the_advisor_is_unchanged():
    assert intent_model.predict("my bill is wrong") is None          # ADVISOR_INTENT_MODEL=0 in the tests (conftest.py)
    assert advisor.suggest("I was charged twice")["intentModel"] is None


def test_every_passage_and_cluster_the_intent_model_points_to_exists():
    assert {t for ts in intent_model.PASSAGES.values() for t in ts} <= {d["title"] for d in advisor.KB}
    assert set(engine.INTENT_CLUSTER.values()) <= set(engine.CLUSTERS)
    assert set(engine.INTENT_CLUSTER) <= set(intent_model.PASSAGES)


def test_the_complaint_agent_asks_the_intent_model_only_when_no_rule_matches(monkeypatch):
    now = dt.datetime(2026, 11, 6, 9, 0)
    monkeypatch.setattr(intent_model, "predict", _fake("report_poor_signal_coverage"))
    case = engine.triage("Since Monday my mobile shows no bars at home and I cannot call anyone", None, now)
    assert case["clusterKey"] == "network" and case["clusterBy"].startswith("intent model")
    ruled = engine.triage("I was charged twice for the same bill", None, now)
    assert ruled["clusterKey"] == "billing_duplicate" and ruled["clusterBy"] == "rules"


REAL = intent_model.DEFAULT_DIR


@pytest.mark.skipif(not (REAL / "config.json").exists(), reason="the trained model files are not on this machine")
def test_the_real_model_reads_paraphrases(monkeypatch):
    monkeypatch.setenv("ADVISOR_INTENT_MODEL", str(REAL))
    intent_model._load.cache_clear(); intent_model.predict.cache_clear()
    try:
        if not intent_model.available():
            pytest.skip("onnxruntime/tokenizers (requirements-models.txt) are not installed")
        assert intent_model.predict("I was charged twice this month and I want my money back")["intent"] == "dispute_invoice"
        assert intent_model.predict("I want to cancel my subscription")["intent"] == "cancel_plan"
        assert intent_model.info()["hand_written_examples"] == 30
    finally:
        intent_model._load.cache_clear(); intent_model.predict.cache_clear()
