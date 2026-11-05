import sys
sys.path.insert(0, "src")
from customer_simulator.schemas import EmotionState, AdvisorSignals, Scenario
from customer_simulator.emotion import update_emotion, decide_action
from customer_simulator.generator import generate_profile, load_personas
from customer_simulator import CustomerSimulatorAgent
from customer_simulator.llm import MockLLM


def test_six_personas():
    p = load_personas()
    assert len(p) == 6
    assert {(x.language, x.gender) for x in p.values()} == {
        (l, g) for l in ("fr", "en", "derja") for g in ("F", "M")}


def test_bad_answer_raises_frustration():
    s = EmotionState()
    assert update_emotion(s, AdvisorSignals(relevance=0.1)).frustration > s.frustration


def test_good_answer_lowers_frustration():
    s = EmotionState(frustration=0.5)
    assert update_emotion(s, AdvisorSignals(relevance=0.9, empathy=0.9, resolved=True)).frustration < s.frustration


def test_thresholds():
    assert decide_action(EmotionState(frustration=0.9, patience=0.05)) == "hangup"
    assert decide_action(EmotionState(frustration=0.8, patience=0.5)) == "escalate"
    assert decide_action(EmotionState()) == "continue"


def test_seed_reproducible():
    a, _ = generate_profile(Scenario(persona_id="fr_f", seed=1))
    b, _ = generate_profile(Scenario(persona_id="fr_f", seed=1))
    assert a == b


def test_every_persona_runs_end_to_end():
    for pid in load_personas():
        ag = CustomerSimulatorAgent(MockLLM())
        assert ag.start(Scenario(persona_id=pid, seed=3)).text
        assert ag.reply("Veuillez patienter.").text


def test_exhausted_patience_triggers_action():
    assert decide_action(EmotionState(patience=0.02, frustration=0.5)) == "hangup"
    assert decide_action(EmotionState(patience=0.1, frustration=0.3)) == "escalate"


def test_frustration_cannot_jump():
    s = EmotionState(frustration=0.5)
    n = update_emotion(s, AdvisorSignals(relevance=0.0, repeated_question=True, wait_seconds=120), 5)
    assert n.frustration <= 0.75 + 1e-9


def test_closing_line_comes_from_llm_or_fallback():
    ag = CustomerSimulatorAgent(MockLLM())
    ag.start(Scenario(persona_id="fr_m", seed=1))
    m = ag._final("Au revoir", "escalate", AdvisorSignals())
    assert m.action == "escalate" and m.text


class RepeatLLM:
    """Se répète tant qu'on ne lui impose pas de changer."""
    def complete(self, system, messages, max_tokens=300, json_mode=False):
        if json_mode:
            return '{"relevance": 0.5, "empathy": 0.5, "repeated_question": false, "resolved": false}'
        if "Ne répète pas" in messages[-1]["content"]:
            return "Mon numéro est le 22 345 678, c'est bien clair maintenant."
        return "Je veux ma facture corrigée tout de suite."


def test_repetition_guard():
    ag = CustomerSimulatorAgent(RepeatLLM())
    first = ag.start(Scenario(persona_id="fr_f", seed=1))
    second = ag.reply("Pouvez-vous me donner votre numéro ?")
    assert first.text != second.text


def test_profile_has_details():
    p, _ = generate_profile(Scenario(persona_id="derja_f", seed=2))
    assert "numéro de ligne" in p.details and "référence de facture" in p.details


def test_history_starts_with_user():
    ag = CustomerSimulatorAgent(MockLLM())
    ag.start(Scenario(persona_id="fr_f", seed=1))
    ag.reply("Bonjour")
    assert ag._window()[0]["role"] == "user"


def test_heuristic_evaluator():
    import json
    from customer_simulator.llm import HeuristicEvalLLM
    h = HeuristicEvalLLM()
    ev = lambda adv: json.loads(h.complete("", [{"role": "user", "content": f"Client : ma facture est fausse\nConseiller : {adv}"}], json_mode=True))
    assert ev("Veuillez patienter un instant.")["relevance"] <= 0.25
    r = ev("Je suis désolé, j'ai corrigé votre facture, c'est réglé.")
    assert r["resolved"] and r["relevance"] >= 0.8 and r["empathy"] > 0.5


def test_agent_records_timings():
    ag = CustomerSimulatorAgent(MockLLM())
    ag.start(Scenario(persona_id="fr_f", seed=1))
    ag.reply("Bonjour madame, comment puis-je vous aider ?")
    assert {"eval", "gen"} <= set(ag.timings)


def test_random_pick_is_fr_en_only_by_default():
    for seed in range(40):
        p, _ = generate_profile(Scenario(seed=seed))
        assert p.language in ("fr", "en")
