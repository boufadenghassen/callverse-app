"""The human-agreement study: the sheet is blind and complete, and the agreement maths is right."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quality_analyst import engine  # noqa: E402
from quality_analyst.labelling import agreement, make_sheet  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = tmp_path_factory.mktemp("labelling")
    html, key = make_sheet.build(folder)
    return html.read_text(encoding="utf-8"), json.loads(key.read_text(encoding="utf-8"))


def sheet_data(html: str) -> dict:
    start = html.index("const DATA = ") + len("const DATA = ")
    return json.loads(html[start:html.index(";\nconst STORE")].replace("<\\/", "</"))


def test_the_sheet_has_fifty_calls_and_every_rule_explained(built):
    html, key = built
    data = sheet_data(html)
    assert len(data["calls"]) == 50 and set(key["calls"]) == {c["id"] for c in data["calls"]}
    assert {r["id"] for g in data["groups"] for r in g["rules"]} == set(engine.RULES)
    assert all(r["def"] for g in data["groups"] for r in g["rules"])
    fired = {r for k in key["calls"].values() for r in k["analyst"]}
    assert len(fired) >= 12, "the chosen calls should exercise most rules"


def test_the_sheet_is_blind(built):
    html, key = built
    data = sheet_data(html)
    assert set(data) == {"sheet", "groups", "facts", "calls"}
    assert all(set(c) == {"id", "turns"} for c in data["calls"])          # no analyst result, no expected labels, no source
    assert all(set(t) <= {"who", "text", "mood", "time"} for c in data["calls"] for t in c["turns"])
    assert "answer-key" not in html


def labels(key, who, rule_of):
    return dict(labeller=who, calls={cid: dict(done=True, rules=rule_of(cid, k)) for cid, k in key["calls"].items()})


def test_agreement_maths(built):
    _, key = built
    same = lambda cid, k: k["analyst"]                       # noqa: E731
    a, b = labels(key, "A", same), labels(key, "B", same)
    text = agreement.report(key, [a, b])
    assert "kappa 1.0" in text and "F1  100%" in text
    flipped = labels(key, "B", lambda cid, k: [] if cid.endswith("1") else k["analyst"])
    assert "Calls where the two people differ" in agreement.report(key, [a, flipped])
    assert agreement.kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert agreement.kappa([True, True, False, False], [True, False, True, False]) == 0.0
    assert agreement.prf([True, True, False], [True, False, True])["f1"] == 0.5
