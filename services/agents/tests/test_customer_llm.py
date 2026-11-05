"""Sami's customer agent inside the live call: the language model writes her words, the rules keep her mood, patience and churn."""
import customer
import customer_llm
import local_llm


def _call():
    return customer.start("ANGRY_PREMIUM", None, "MEDIUM", "BILLING", False)["id"]


def test_without_the_model_the_rules_write_her_line_as_before():
    sid = _call()
    r = customer.say(sid, "Let me transfer you to the billing team.")
    assert r["writer"] == "rules" and r["client"]


def test_the_model_writes_her_line_and_knows_her_mood(monkeypatch):
    seen = {}

    def fake(system, user, **kw):
        seen["system"], seen["user"] = system, user
        return {"line": "Another transfer? I pay premium for this?"}
    monkeypatch.setattr(customer_llm, "enabled", lambda: True)
    monkeypatch.setattr(local_llm, "chat_json", fake)
    sid = _call()
    rules = customer.replay("ANGRY_PREMIUM", None, "MEDIUM", "BILLING", False, ["TRANSFER"], ["Let me transfer you."])
    r = customer.say(sid, "Let me transfer you.")
    assert r["client"] == "Another transfer? I pay premium for this?" and r["writer"] == "language model"
    assert (r["mood"], r["patience"]) == (rules.turns[-1].mood, rules.turns[-1].patience)       # the rules still decide the numbers
    assert f"mood {r['mood']}/100" in seen["system"] and "advisor: Let me transfer you." in seen["user"]
    turns, _, _ = customer.transcript(sid)
    assert turns[-1]["text"] == "Another transfer? I pay premium for this?"                      # the quality analyst reviews what she said


def test_a_repeated_line_is_retried_once_then_the_rules_take_over(monkeypatch):
    calls = []
    monkeypatch.setattr(customer_llm, "enabled", lambda: True)
    monkeypatch.setattr(local_llm, "chat_json", lambda system, user, **kw: calls.append(user) or {"line": "I was charged twice on my September bill."})
    sid = _call()
    r = customer.say(sid, "Could you explain the problem again?")
    assert len(calls) == 2 and "Do not repeat" in calls[1] and r["writer"] == "rules"


def test_no_answer_from_the_model_falls_back_to_the_rules(monkeypatch):
    monkeypatch.setattr(customer_llm, "enabled", lambda: True)
    monkeypatch.setattr(local_llm, "chat_json", lambda *a, **k: None)
    sid = _call()
    assert customer.say(sid, "I am sorry, I understand how frustrating this is.")["writer"] == "rules"
