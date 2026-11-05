"""Run from services/agents:  python -m pytest -q   (uses knowledge/comcast_sample.csv unless the full Comcast.csv is in datasets/)"""
import sys
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import complaints  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def row(text, status="Open", proxy="No", ticket="1"):
    return pd.Series(dict(text=text, status=status, proxy=proxy, ticket=ticket))


def test_a_legal_threat_over_money_scores_higher_than_a_plain_complaint():
    risky, _ = complaints.score(row("Charged twice again, I will sue and call the FCC"))
    plain, _ = complaints.score(row("Internet complaint"))
    assert risky > plain + 30


def test_every_score_comes_with_readable_reasons_and_stays_in_range():
    risk, reasons = complaints.score(row("Refused refund, fraud, charged twice again, will cancel, no one helps", status="Pending", proxy="Yes"))
    assert 0 <= risk <= 100
    assert any("Legal" in r for r in reasons) and any("Money" in r for r in reasons) and any("Pending" in r for r in reasons)


def test_topic_rules_pick_the_expected_root_cause():
    assert complaints.topic_of("Throttling service and unreasonable data caps") == "Data caps and throttling"
    assert complaints.topic_of("Billing after service was asked to be disconnected") == "Billing and fees"
    assert complaints.topic_of("Internet Disconnects Every Night") == "Outages and disconnections"
    assert complaints.topic_of("Horrible Internet Service") == complaints.OTHER


def test_only_open_and_pending_cases_are_listed_riskiest_first():
    cases = complaints.open_cases()
    assert cases and all(c["status"].lower() in complaints.OPEN_STATUSES for c in cases)
    risks = [c["escalationRisk"] for c in cases]
    assert risks == sorted(risks, reverse=True)
    assert {"id", "summary", "severity", "escalationRisk", "cluster", "hoursLeft"} <= set(cases[0])   # the web app's contract


def test_scores_are_deterministic():
    assert complaints.open_cases() == complaints.open_cases()


def test_escalate_moves_a_case_up_one_lane_and_assign_sets_the_owner():
    complaints._actions.clear()
    case = next(c for c in complaints.open_cases(10_000) if c["severity"] == "Medium")
    up = complaints.escalate(case["id"])
    assert up["severity"] == "High"
    assert complaints.assign(case["id"], "Amine")["owner"] == "Amine"
    complaints._actions.clear()


def test_clusters_cover_every_complaint():
    total = sum(c["cases"] for c in complaints.clusters())
    assert total == len(complaints.load_cases())


def test_http_endpoints():
    cases = client.get("/complaints/cases?limit=3").json()
    assert 1 <= len(cases) <= 3
    cid = cases[0]["id"]
    assert client.get(f"/complaints/cases/{cid}").json()["id"] == cid
    assert client.get("/complaints/cases/CMP-nope-nope").status_code == 404
    assert client.get("/complaints/cases/bad id").status_code in (404, 422)
    assert client.post(f"/complaints/cases/{cid}/assign", json={"owner": "Amine"}).json()["owner"] == "Amine"
    assert "topics" in client.get("/complaints/clusters").json()
    assert "open" in client.get("/complaints/summary").json()
    complaints._actions.clear()
