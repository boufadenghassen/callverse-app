"""Complaint agent tests. Run from services/agents:  ../../../venv/Scripts/python.exe -m pytest -q complaints_agent/tests"""
import datetime as dt
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from complaints_agent import engine, store  # noqa: E402
from main import app  # noqa: E402
from quality_analyst import store as quality_store  # noqa: E402

client = TestClient(app)
NOW = dt.datetime(2026, 10, 22, 12, 0)


@pytest.fixture(autouse=True)
def databases(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPLAINTS_DB", str(tmp_path / "complaints.db"))
    monkeypatch.setenv("QUALITY_DB", str(tmp_path / "quality.db"))


def case(text, customer=None, hours_ago=1, status="open", **extra):
    return dict(id="X", customer=customer, text=text, summary=engine.short(text), opened_at=NOW - dt.timedelta(hours=hours_ago), status=status, assigned=None, override=None,
                channel="call", source="agent", **extra)


def test_money_is_read_from_the_customers_words():
    assert engine.parse_amount("I was charged twice for 180 dinars") == 180
    assert engine.parse_amount("they took $2,000 and then 45.5 TND") == 2000
    assert engine.parse_amount("it is about 12 DT") == 12
    assert engine.parse_amount("I called 3 times about my bill") is None                 # a number that is not money


def test_the_root_cause_is_the_cluster_with_the_most_phrases():
    assert engine.classify("I was charged twice on my bill")[0] == "billing_duplicate"
    assert engine.classify("My roaming bundle did not work abroad")[0] == "roaming"
    assert engine.classify("My internet has been slow for weeks")[0] == "network"
    assert engine.classify("The cancellation fee is unfair")[0] == "contract_terms"
    key, extra = engine.classify("Roaming abroad failed and I was charged twice for it")
    assert key in ("roaming", "billing_duplicate") and extra                               # the other one is listed too
    assert engine.classify("Hello, I have a question")[0] == "other"


def test_severity_is_a_sum_of_named_factors_and_follows_what_is_at_stake():
    plain = engine.analyse(case("My data ran out in two days, I think the usage is wrong."), [], NOW)
    legal = engine.analyse(case("My data ran out. I will contact a lawyer and the consumer protection association."), [], NOW)
    big = engine.analyse(case("I was charged twice for 450 dinars and I will post this online."), [], NOW)
    for a in (plain, legal, big):
        assert a["severityScore"] == max(0, min(100, sum(f["points"] for f in a["severityFactors"])))
        assert a["severity"] == engine.level_of(a["severityScore"])
        assert all(f["why"] for f in a["severityFactors"])
    assert plain["severity"] == "Low" and legal["severityScore"] > plain["severityScore"]
    assert {f["name"] for f in big["severityFactors"]} == {"Money at stake", "Public exposure"}
    assert next(f for f in big["severityFactors"] if f["name"] == "Money at stake")["points"] == 25


def test_a_repeat_customer_with_value_is_more_serious_and_more_likely_to_escalate():
    text = "I was charged twice for 120 dinars on my bill."
    new = engine.analyse(case(text, "MS-0007"), [], NOW)                                  # a two-week-old customer, first contact
    earlier = [dict(case("Duplicate charge last month.", "YT-1042", hours_ago=24 * 10), id="Y1"), dict(case("Another duplicate.", "YT-1042", hours_ago=24 * 3), id="Y2")]
    loyal = engine.analyse(case(text, "YT-1042"), earlier, NOW)                           # six years with us and two earlier cases
    assert loyal["contacts"] == 2 and new["contacts"] == 0
    assert loyal["severityScore"] > new["severityScore"] and loyal["escalationRisk"] > new["escalationRisk"]
    names = {f["name"] for f in loyal["severityFactors"]}
    assert {"Customer value", "Repeat contact"} <= names
    third = engine.analyse(case("This is the third time I contact you about the same charge.", "MS-0007"), [], NOW)
    assert third["contacts"] == 2                                                          # "the third time" counts as two earlier contacts


def test_the_deadline_comes_from_the_level_and_time_pressure_raises_the_risk():
    text = "I was charged twice for 180 dinars and I will post this online."
    fresh = engine.analyse(case(text, hours_ago=1), [], NOW)
    sla = fresh["deadline"]["slaHours"]
    late = engine.analyse(case(text, hours_ago=0.8 * sla), [], NOW)
    over = engine.analyse(case(text, hours_ago=1.5 * sla), [], NOW)
    assert sla == engine.sla_hours(fresh["severity"])
    assert fresh["hoursLeft"] == round(fresh["deadline"]["slaHours"] - 1, 1)
    assert fresh["escalationRisk"] < late["escalationRisk"] < over["escalationRisk"]
    assert over["deadline"]["overdue"] and over["warning"] and "past its deadline" in over["warning"]["why"]
    assert fresh["warning"] is None
    names = {f["name"] for f in over["riskFactors"]}
    assert "Time pressure" in names
    for a in (fresh, late, over):
        assert a["escalationRisk"] == max(0, min(100, sum(f["points"] for f in a["riskFactors"])))


def test_the_first_actions_come_with_their_reasons_and_respect_the_refund_limit():
    a = engine.analyse(case("I was charged twice for 180 dinars. I will go to the consumer protection association.", hours_ago=30), [], NOW)
    by = {x["action"]: x for x in a["actions"]}
    assert any("supervisor's approval" in k and "50 TND limit" in v["why"] for k, v in by.items())
    assert any("compliance" in k.lower() for k in by) and any("Apologise" in k for k in by)
    assert all(x["why"] and x["who"] for x in a["actions"]) and "call back after 72 h" in a["actions"][-1]["action"]
    small = engine.analyse(case("I was charged twice for 20 dinars."), [], NOW)
    assert not any("supervisor's approval" in x["action"] for x in small["actions"])


def test_a_case_goes_from_open_to_taken_to_resolved_to_closed_and_every_step_is_logged():
    c = store.create("My internet has been slow for weeks.", "SH-5520", at=NOW - dt.timedelta(hours=5))
    cid = c["id"]
    assert cid.startswith("CMP-") and c["level_open"] and c["sla_hours"] == engine.sla_hours(c["level_open"])
    assert store.act(cid, "take", "amine", at=NOW)["status"] == "taken"
    with pytest.raises(ValueError):
        store.act(cid, "close", "amine", trusted=True)                                      # not resolved yet
    with pytest.raises(ValueError):
        store.act(cid, "resolve", "amine", resolution="magic")
    store.act(cid, "resolve", "amine", "fixed the cell", NOW, resolution="fixed")
    assert store.get(cid)["status"] == "resolved" and [f["id"] for f in store.follow_ups(NOW)] == [cid]
    assert store.follow_ups(NOW)[0]["dueInHours"] == engine.FOLLOW_UP_HOURS
    store.act(cid, "close", "amine", at=NOW + dt.timedelta(hours=72), trusted=True)
    done = store.get(cid)
    assert done["status"] == "closed" and done["trusted"] == 1 and store.follow_ups(NOW) == []
    kinds = [e["kind"] for e in store.events(cid)]
    assert kinds == ["opened", "taken", "resolved", "closed"]


def test_a_customer_who_is_still_unhappy_reopens_the_case():
    cid = store.create("Charged twice for 90 dinars.", "WF-3391", at=NOW - dt.timedelta(hours=2))["id"]
    store.act(cid, "resolve", "amine", at=NOW, resolution="refunded")
    store.act(cid, "close", "amine", at=NOW + dt.timedelta(hours=72), trusted=False, note="still waiting for the refund")
    c = store.get(cid)
    assert c["status"] == "open" and c["trusted"] == 0 and c["resolution"] is None
    assert store.events(cid)[-1]["kind"] == "reopened" and "trust not restored" in store.events(cid)[-1]["note"]
    with pytest.raises(ValueError):
        store.act(cid, "reopen", "amine")                                                   # it is open already


def test_escalating_moves_a_case_up_one_level_and_alerting_is_remembered():
    cid = store.create("My data ran out in two days.", "MS-0007", at=NOW - dt.timedelta(hours=1))["id"]
    before = engine.analyse(store.get(cid), store.all_cases(), NOW)["severity"]
    store.act(cid, "escalate", "amine", at=NOW)
    after = engine.analyse(store.get(cid), store.all_cases(), NOW)
    assert engine.ORDER.index(after["severity"]) == engine.ORDER.index(before) - 1 and after["overridden"]
    store.act(cid, "severity", "amine", at=NOW, level="Critical")
    assert engine.analyse(store.get(cid), store.all_cases(), NOW)["severity"] == "Critical"
    with pytest.raises(ValueError):
        store.act(cid, "severity", "amine", level="Urgent")
    assert not store.alerted(cid)
    store.act(cid, "alert", "amine", at=NOW)
    assert store.alerted(cid)
    d = store.detail(cid, NOW)
    assert not any("Alert a supervisor now" in a["action"] for a in d["actions"])           # already done


def test_the_simulated_history_is_made_once_and_today_is_what_the_page_shows():
    store.ensure_history(NOW)
    store.ensure_history(NOW)
    cases = store.all_cases()
    assert len(cases) == 8 + 38 and {c["id"] for c in cases} >= {"CMP-221", "CMP-219", "CMP-214"}
    live = store.analysed(NOW, ("open", "taken"))
    assert len(live) == 6 and live[0]["id"] == "CMP-221"                                    # the most dangerous first
    top = live[0]
    assert top["severity"] == "Critical" and top["escalationRisk"] >= 80 and top["warning"] and top["contacts"] >= 2
    assert [a["id"] for a in live if a["deadline"]["overdue"]] == ["CMP-225"]
    assert next(a for a in live if a["id"] == "CMP-223")["cluster"] == "Network and service quality"


def test_the_insights_show_root_causes_trends_and_how_well_the_team_does():
    store.ensure_history(NOW)
    ins = store.insights(NOW)
    assert ins["open"] == 6 and sum(ins["byLevel"].values()) == 6 and ins["warnings"] >= 1 and ins["overdue"] == 1
    assert len(ins["weeks"]) == 8 and sum(ins["weeks"]) <= len(store.all_cases())
    assert 0 < ins["slaMetRate"] < 1 and 0 < ins["trustRate"] <= 1 and ins["resolved"] > 20
    roaming = next(r for r in ins["clusters"] if r["key"] == "roaming")
    assert roaming["trend"] > 0 and roaming["last28"] == roaming["previous28"] + roaming["trend"]      # simulated to rise in the last weeks
    assert roaming["worked"]["label"] and roaming["worked"]["count"] <= roaming["worked"]["of"]
    assert abs(sum(c["share"] for c in ins["causes"]) - 1) < 0.02


def test_a_case_in_detail_has_its_history_its_log_and_what_worked_on_similar_cases():
    store.ensure_history(NOW)
    d = store.detail("CMP-221", NOW)
    assert d["customerFile"]["name"] == "Yasmine Toumi" and d["text"].startswith("I was charged twice")
    assert [e["kind"] for e in d["events"]] == ["opened"] and len(d["earlier"]) >= 2
    assert d["worked"]["label"] == "Refund or credit given" and d["worked"]["count"] <= d["worked"]["of"]
    assert d["similar"] and all(s["resolution"] for s in d["similar"])
    with pytest.raises(KeyError):
        store.detail("CMP-999999", NOW)


def test_the_api_lists_triages_opens_and_acts_and_refuses_what_is_wrong():
    store.ensure_history()
    open_ = client.get("/complaints/open").json()
    assert open_ and {"id", "summary", "severity", "escalationRisk", "cluster", "hoursLeft"} <= set(open_[0])          # the web contract's five fields come first
    assert [a["escalationRisk"] for a in open_] == sorted((a["escalationRisk"] for a in open_), reverse=True)
    before = len(store.all_cases())
    t = client.post("/complaints/triage", json={"text": "I was charged twice for 300 dinars and I will sue.", "customer_id": "YT-1042"}).json()
    assert t["severity"] in ("Critical", "High") and t["id"] == "NEW" and t["severityFactors"] and t["actions"]
    assert len(store.all_cases()) == before                                                         # triage saves nothing
    assert client.post("/complaints/triage", json={"text": "short"}).status_code == 422
    assert client.post("/complaints/triage", json={"text": "I was charged twice, really.", "customer_id": "ZZ-0000"}).status_code == 404
    made = client.post("/complaints", json={"text": "My roaming pass did not work in Turkey.", "channel": "email", "customer_id": "IK-2210"}).json()
    cid = made["id"]
    assert made["status"] == "open" and made["cluster"] == "Roaming activation" and len(store.all_cases()) == before + 1
    assert client.get(f"/complaints/{cid}").json()["id"] == cid
    assert client.get("/complaints/CMP-999999").status_code == 404 and client.get("/complaints/not-an-id").status_code == 404
    take = client.post(f"/complaints/{cid}/take", json={"by": "amine"}).json()
    assert take["status"] == "taken" and take["assigned"] == "amine"
    assert client.post(f"/complaints/{cid}/close", json={"by": "amine", "trusted": True}).status_code == 422       # not resolved yet
    assert client.post(f"/complaints/{cid}/resolve", json={"by": "amine"}).status_code == 422                       # how?
    assert client.post(f"/complaints/{cid}/resolve", json={"by": "amine", "resolution": "fixed", "note": "reactivated"}).json()["resolution"] == "Fault fixed"
    assert client.post(f"/complaints/{cid}/dance", json={"by": "amine"}).status_code == 404
    assert client.post(f"/complaints/{cid}/take", json={"by": "<script>"}).status_code == 422
    assert client.post("/complaints/CMP-999999/take", json={"by": "amine"}).status_code == 404
    waiting = client.get("/complaints/follow-ups").json()
    assert cid in [f["id"] for f in waiting] and [f["dueInHours"] for f in waiting] == sorted(f["dueInHours"] for f in waiting)
    assert client.get("/complaints/insights").json()["open"] == len(open_)


def test_complaints_can_start_from_calls_the_quality_analyst_scored():
    quality_store.ensure_history()
    store.ensure_history()
    found = client.get("/complaints/from-calls").json()
    assert found and all(f["why"] and f["triage"]["id"] == "NEW" for f in found)
    first = found[0]
    case = client.post("/complaints/from-call", json={"call_id": first["callId"]}).json()
    assert case["source"] == "quality" and case["callId"] == first["callId"] and case["text"] == first["text"]
    assert first["callId"] not in {f["callId"] for f in client.get("/complaints/from-calls").json()}                # it is a complaint now
    assert client.post("/complaints/from-call", json={"call_id": first["callId"]}).status_code == 409
    assert client.post("/complaints/from-call", json={"call_id": "CALL-1"}).status_code == 404
    assert client.post("/complaints/from-call", json={"call_id": "nope"}).status_code == 422
