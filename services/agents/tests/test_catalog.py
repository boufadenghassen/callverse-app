import json

import pytest

from scenario_gen.catalog import Catalog, CatalogError, compare_with_sim_intents, intent_keys_from_file, normalize_key


def test_catalog_loads_and_is_consistent(catalog):
    assert len(catalog.intents) >= 12
    assert {"en", "fr", "derja"} <= set(catalog.languages)
    for intent in catalog.intents.values():
        for lang in catalog.languages:
            assert intent.card[lang].strip()
        assert intent.success_criteria


def test_derja_cards_are_arabic_script(catalog):
    for intent in catalog.intents.values():
        assert any("؀" <= ch <= "ۿ" for ch in intent.card["derja"]), intent.key


def test_every_emotion_is_covered(catalog):
    emotions = {i.opening_emotion for i in catalog.intents.values()}
    assert emotions == {"anger", "disgust", "fear", "happy", "neutral", "sad"}


def test_there_are_rare_and_normal_events(catalog):
    assert any(e.rare for e in catalog.events.values())
    assert sum(not e.rare for e in catalog.events.values()) >= 5


def test_unknown_skill_in_catalog_is_rejected():
    raw = json.loads(open("scenario_gen/data/catalog.json", encoding="utf-8").read())
    raw["intents"][0]["skills"] = ["telepathy"]
    with pytest.raises(CatalogError):
        Catalog(raw)


def test_criterion_names_are_matched_leniently(catalog):
    assert normalize_key("Respect des procédures") == "respect_des_procedures"
    assert catalog.criterion_to_skills("Conformité") == [("procedure_compliance", 1.0)]
    assert catalog.criterion_to_skills("Exactitude") == [("accuracy", 1.0)]
    assert catalog.criterion_to_skills("empathy") == [("empathy", 1.0)]
    assert catalog.criterion_to_skills("something else") is None


def test_every_criterion_of_the_real_quality_analyst_is_understood(catalog):
    """The coach reads the Quality Analyst's own criterion names; none may be ignored as unknown."""
    from quality_analyst.engine import CRITERIA
    for name in CRITERIA:
        assert catalog.criterion_to_skills(name), name
    assert [skill for skill, _ in catalog.criterion_to_skills("Communication")] == ["active_listening", "empathy"]
    assert catalog.criterion_to_skills("Customer sentiment") == catalog.criterion_to_skills("sentiment")


def test_restrict_to_the_sims_intents(tmp_path, catalog):
    path = tmp_path / "intents.json"
    path.write_text(json.dumps({"double_billing": {}, "line_cut": {}, "other_thing": {}}), encoding="utf-8")
    report = compare_with_sim_intents(catalog, path)
    assert report["shared"] == ["double_billing", "line_cut"]
    assert "other_thing" in report["sim_not_covered_by_us"]
    assert "cancellation_request" in report["ours_unknown_to_sim"]
    catalog.restrict_intents(intent_keys_from_file(path))
    assert set(catalog.intents) == {"double_billing", "line_cut"}


def test_intents_file_can_be_a_list(tmp_path):
    path = tmp_path / "intents.json"
    path.write_text(json.dumps([{"key": "a"}, {"id": "b"}, "c"]), encoding="utf-8")
    assert intent_keys_from_file(path) == {"a", "b", "c"}
