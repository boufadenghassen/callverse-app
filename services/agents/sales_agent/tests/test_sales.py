"""Sales agent: needs found in what the customer says, offers ranked with their reasons in points, outcomes that feed the ranking."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import advisor  # noqa: E402
from main import app  # noqa: E402
from sales_agent import engine, store  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_DB", str(tmp_path / "sales.db"))


def C(text, mood=None, start=0):
    return dict(speaker="customer", text=text, start=start, **({} if mood is None else {"mood": mood}))


def test_needs_come_from_the_customers_own_words_with_a_quote_and_a_time():
    needs = engine.conversation_needs([C("Hello. I am travelling to Paris next week for work.", start=14), dict(speaker="advisor", text="I need to call my wife.", start=20)])
    assert set(needs) == {"travel"}                                   # the advisor's words are not the customer's needs
    assert needs["travel"]["time"] == "00:14" and "Paris" in needs["travel"]["quote"] and needs["travel"]["strength"] == 0.7
    again = engine.conversation_needs([C("My data ran out.", start=1), C("It ran out again this week, I need more data.", start=9)])
    assert again["data_short"]["mentions"] == 2 and again["data_short"]["strength"] > 0.7      # said twice: stronger


def test_a_denied_need_is_not_a_need():
    assert "leaving" not in engine.conversation_needs([C("I am not leaving, I just want to understand my bill.")])
    assert "leaving" in engine.conversation_needs([C("If this goes on I will cancel my subscription.")])


def test_the_offers_follow_the_need_and_respect_the_contract():
    ines = advisor.get_customer("IK-2210")                            # Premium Unlimited: roaming and data are already covered
    ranked, skipped = engine.recommend(ines, engine.conversation_needs([C("I am going abroad next week and I will need data.")]), 60)
    assert ranked == [] and {s["offerId"] for s in skipped} >= {"roaming-pass", "data-booster"}
    assert all("Premium Unlimited" in s["why"] for s in skipped)
    mounir = advisor.get_customer("MS-0007")                          # Starter, two weeks old
    ranked, skipped = engine.recommend(mounir, engine.conversation_needs([C("I want to cancel, it is too expensive.")]), 60)
    assert "loyalty-discount" not in {r["offerId"] for r in ranked}   # a retention discount needs a year of tenure
    assert any(s["offerId"] == "loyalty-discount" and "tenure" in s["why"] for s in skipped)
    ranked, _ = engine.recommend(mounir, engine.conversation_needs([C("Can I switch to a bigger plan?")]), 60)
    assert ranked[0]["offer"] == "Upgrade to Mobile Basic 20 GB"


def test_a_relevance_is_the_sum_of_named_factors_and_says_what_would_change_it():
    yasmine = advisor.get_customer("YT-1042")                         # one open ticket, impatient
    ranked, _ = engine.recommend(yasmine, engine.file_needs(yasmine), 45)
    top = ranked[0]
    assert top["relevance"] == sum(f["points"] for f in top["factors"])
    assert {f["name"] for f in top["factors"]} >= {"What the file says", "Fit with the contract", "The moment"}
    moment = next(f for f in top["factors"] if f["name"] == "The moment")
    assert moment["points"] < 0 and top["timing"]["cue"] == "after_resolution"
    solved = dict(yasmine, openTickets=0)                             # what the counterfactual promises really happens
    assert f"would be {engine.recommend(solved, engine.file_needs(solved), 45)[0][0]['relevance']}" in top["counterfactual"]


def test_the_moment_matters_but_a_retention_offer_suits_an_upset_customer():
    salma = advisor.get_customer("SH-5520")                           # angry, usage down 45 %
    spoken = engine.conversation_needs([C("I want to cancel and my internet is slow, I am furious.", mood=20)])
    ranked, _ = engine.recommend(salma, engine.merge_needs(spoken, engine.file_needs(salma)), 20)
    by = {r["offerId"]: r for r in ranked}
    assert by["loyalty-discount"]["timing"]["cue"] == "now" and by["data-booster"]["timing"]["cue"] == "after_resolution"
    assert ranked[0]["offerId"] == "loyalty-discount"


def test_the_track_record_moves_the_ranking_a_little():
    mounir = advisor.get_customer("MS-0007")
    needs = engine.conversation_needs([C("I run out of data every month.")])
    plain = engine.recommend(mounir, needs, 60)[0][0]["relevance"]
    loved = engine.recommend(mounir, needs, 60, {"data-booster": (50, 45)})[0][0]
    hated = engine.recommend(mounir, needs, 60, {"data-booster": (50, 2)})[0][0]
    assert loved["relevance"] > plain > hated["relevance"] and loved["relevance"] - hated["relevance"] <= 20
    assert any(f["name"] == "Track record" for f in loved["factors"])


def test_the_history_is_simulated_once_and_the_analytics_read_it():
    store.ensure_history()
    store.ensure_history()
    a = store.analytics()
    assert a["total"] == 240 and a["simulated"] == 240 and 0 < a["rate"] < 1
    assert {r["key"] for r in a["byMoment"]} == {"now", "after_resolution"}
    assert next(r for r in a["byRelevance"] if r["key"] == "70+")["rate"] > next(r for r in a["byRelevance"] if r["key"] == "under 50")["rate"]   # as simulated


def test_the_api_lists_detects_records_and_validates():
    assert len(client.get("/sales/opportunities").json()) >= 3
    ok = client.post("/sales/detect", json=dict(customer_id="MS-0007", turns=[dict(speaker="customer", text="I run out of data and my wife needs a line too.", start=3)])).json()
    assert {s["need"] for s in ok["signals"]} >= {"data_short", "family"} and ok["offers"][0]["factors"]
    assert client.post("/sales/detect", json=dict(customer_id="ZZ-0000", turns=[dict(speaker="customer", text="hi")])).status_code == 404
    assert client.post("/sales/detect", json=dict(customer_id="nope", turns=[dict(speaker="customer", text="hi")])).status_code == 422
    assert client.post("/sales/detect", json=dict(turns=[])).status_code == 422
    assert client.post("/sales/outcome", json=dict(customer_id="MS-0007", offer_id="nothing", outcome="accepted")).status_code == 404
    before = client.get("/sales/analytics").json()["total"]
    assert client.post("/sales/outcome", json=dict(customer_id="MS-0007", offer_id="data-booster", outcome="accepted", relevance=80)).json() == {"recorded": True}
    assert client.get("/sales/analytics").json()["total"] == before + 1
