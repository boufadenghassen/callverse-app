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


def test_churn_risk_is_a_sum_of_named_factors_and_follows_the_customer():
    risk = {c["id"]: engine.churn_risk(c, engine.file_needs(c), engine.MOOD_OF[c["mood"]]) for c in advisor.CUSTOMERS}
    for r in risk.values():
        assert r["score"] == max(0, min(100, sum(f["points"] for f in r["factors"])))
    assert risk["SH-5520"]["level"] == "High" and risk["WF-3391"]["level"] == "High"               # usage down 45 %, angry; cancelling twice
    assert risk["IK-2210"]["level"] == "Low" and risk["YT-1042"]["level"] == "Low"
    assert sum(f["name"] == "Usage" for f in risk["SH-5520"]["factors"]) == 1 and not any(f["name"] == "Talks about leaving" for f in risk["SH-5520"]["factors"])   # a usage drop is counted once
    said = engine.churn_risk(None, engine.conversation_needs([C("I want to cancel, it is too expensive.", mood=30)]), 30)       # no file: the conversation alone
    assert {f["name"] for f in said["factors"]} >= {"Talks about leaving", "Price", "Mood"}


def test_the_chance_of_a_yes_comes_from_similar_offers_and_is_smoothed():
    rates = {"data-booster": (40, 20)}                                                           # 50 % overall
    assert engine.acceptance("data-booster", 80, "now", None, None) is None                      # no history, no figure
    alone = engine.acceptance("data-booster", 80, "now", rates, {})
    assert alone["probability"] == 0.5 and alone["similar"] == 0 and "overall rate" in alone["basis"]
    few = engine.acceptance("data-booster", 80, "now", rates, {("data-booster", "70+", "now"): (2, 2)})
    many = engine.acceptance("data-booster", 80, "now", rates, {("data-booster", "70+", "now"): (60, 54)})
    assert 0.5 < few["probability"] < 0.7 < many["probability"] <= 0.95                           # two cases barely move it, sixty do
    assert "60 similar offers" in many["basis"] and "54 accepted" in many["basis"]


def test_what_a_yes_is_worth_and_the_retention_offer_can_lose_money():
    rates, cells = store.rates(), store.cells()
    store.ensure_history()
    rates, cells = store.rates(), store.cells()
    mounir = advisor.get_customer("MS-0007")
    top = engine.recommend(mounir, engine.conversation_needs([C("I run out of data every month.")]), 60, rates, cells)[0][0]
    assert top["expected"]["ifYes"] == 108 and top["expected"]["tnd"] == round(108 * top["acceptance"]["probability"])
    salma, yasmine = advisor.get_customer("SH-5520"), advisor.get_customer("YT-1042")
    def retention(customer, mood):
        needs = engine.merge_needs(engine.conversation_needs([C("I want to cancel.")]), engine.file_needs(customer))
        return next(r for r in engine.recommend(customer, needs, mood, rates, cells)[0] if r["offerId"] == "loyalty-discount")["expected"]
    assert retention(salma, 20)["ifYes"] > 0                                                      # 75 % of a 336 TND year is kept, minus the discount
    assert retention(yasmine, 70)["ifYes"] < retention(salma, 20)["ifYes"]                        # the same discount keeps far less when the risk is lower


def test_the_policy_simulation_trades_volume_for_acceptance():
    store.ensure_history()
    r = store.simulate(1000, 30)
    every, strict = r["policies"][0], r["policies"][3]
    assert every["offers"] == 300 and r["opportunities"] == 300                                  # 1000 calls x 30 %
    assert strict["offers"] < every["offers"] and strict["rate"] > every["rate"] and strict["declined"] < every["declined"]
    assert strict["revenue"] <= every["revenue"]                                                  # fewer offers, fewer sales: the refusals are not priced
    assert store.simulate(1000, 30, 70, True)["yours"]["offers"] == strict["offers"]
    assert store.simulate(2000, 30)["policies"][0]["revenue"] == 2 * every["revenue"]            # twice the calls, twice the money


def test_the_new_figures_travel_through_the_api():
    store.ensure_history()                                            # the service does this at start; the test client does not run it
    opps = client.get("/sales/opportunities").json()
    assert all(o["churn"]["level"] in ("Low", "Medium", "High") and "tnd" in o["expected"] for o in opps)
    ok = client.post("/sales/detect", json=dict(customer_id="SH-5520", turns=[dict(speaker="customer", text="I want to cancel.", start=1)])).json()
    assert ok["churn"]["score"] > 60 and ok["offers"][0]["acceptance"]["probability"] > 0
    sim = client.post("/sales/simulate", json=dict(calls=500, share=20, min_relevance=60, good_moment_only=True)).json()
    assert sim["opportunities"] == 100 and len(sim["policies"]) == 4 and sim["yours"]["minRelevance"] == 60
    assert client.post("/sales/simulate", json=dict(calls=0)).status_code == 422
    assert client.post("/sales/simulate", json=dict(min_relevance=101)).status_code == 422
