"""What moved a score: what the advisor said that lowered it, and what protected it. Every effect is a what-if, so the tests re-score the call themselves."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quality_analyst import engine as quality  # noqa: E402
from quality_analyst import store as quality_store  # noqa: E402


def T(who, start, text, mood=None):
    return dict(speaker=who, start=start, end=start + 4, text=text, **({} if mood is None else {"mood": mood}))


BAD = [T("customer", 0, "I was charged twice on my September bill, and this is the third time I call about it.", 22),
       T("advisor", 6, "Yes, could you explain the problem again from the start?"),
       T("customer", 10, "Again, I already told your colleagues everything.", 30),
       T("advisor", 13, "I will refund you 120 dinars right away."),
       T("customer", 18, "Okay, but I have heard that before.", 28),
       T("advisor", 20, "Please hold while I transfer you to the billing team."),
       T("customer", 24, "Another transfer. Unbelievable. I am done. Goodbye.", 29)]
GOOD = [T("customer", 0, "I was charged twice on my bill. This is so frustrating.", 30),
        T("advisor", 5, "Hello, I am sorry about that, I understand how frustrating this is. Before I promise anything let me check the refund policy."),
        T("customer", 12, "Okay.", 45),
        T("advisor", 16, "Can you confirm your date of birth for security? Thank you. I will refund the duplicate and email you a confirmation. Anything else I can help with?"),
        T("customer", 25, "No, thanks.", 70)]


def test_what_lowered_the_score_is_listed_with_its_cost_and_the_words():
    r = quality.review(BAD, "A.", "CALL-1")
    hurt = r["drivers"]["hurt"]
    assert all(d["effect"] <= 0 for d in hurt) and [d["effect"] for d in hurt] == sorted(d["effect"] for d in hurt)
    promise = next(d for d in hurt if d["rule"] == "promise_before_check")
    assert promise["timestamp"] == "00:13" and promise["effect"] < 0 and "refund you 120 dinars" in promise["quote"]
    # the effect is exactly what the score gains without that finding
    without = [e for e in r["errors"] if e["rule"] != "promise_before_check"]
    assert -promise["effect"] == quality.overall(quality.score(without)) - r["overall"]
    assert next(e for e in r["errors"] if e["rule"] == "promise_before_check")["effect"] == promise["effect"]


def test_what_protected_the_score_is_a_real_what_if():
    r = quality.review(GOOD, "A.", "CALL-2")
    assert r["overall"] == 100
    helped = {d["rule"]: d for d in r["drivers"]["helped"]}
    check = helped["check_first"]
    assert check["effect"] > 0 and check["prevents"] == ["Promise before the policy check"]
    # remove the policy check from the call by hand: the score really falls by that much
    neutral = [dict(t) for t in GOOD]
    neutral[1]["text"] = "Hello, I am sorry about that, I understand how frustrating this is."
    assert 100 - quality.review(neutral, "A.", "C")["overall"] >= check["effect"]
    assert helped["mood_up"]["effect"] == 0 and helped["mood_up"]["prevents"] == []       # nothing was at stake: no invented points


def test_effects_are_not_added_up_when_a_criterion_is_already_at_zero():
    err = lambda rule, turn: dict(rule=rule, criterion="Accuracy", points=6, turn=turn, timestamp="00:01", quote="q", reason=rule, fix="f", cause="c")
    review = dict(turns=[T("customer", 0, "hi"), T("advisor", 2, "a"), T("advisor", 4, "b"), T("advisor", 6, "c")],
                  errors=[err("x", 1), err("y", 2), err("z", 3)], strengths=[])
    out = quality.explained(review)
    assert all(e["effect"] == 0 and e["floored"] for e in out["errors"])                 # 18 points lost, but any two still leave Accuracy at 0


def test_a_disputed_finding_leaves_the_drivers_and_the_others_are_recomputed():
    r = quality.review(BAD, "A.", "CALL-1")
    out = quality.rescore(r, {("promise_before_check", 3)})
    assert out["overall"] > r["overall"] and out["adjusted"]
    assert all(d["rule"] != "promise_before_check" for d in out["drivers"]["hurt"])
    assert next(e for e in out["errors"] if e["rule"] == "promise_before_check")["effect"] == 0


def test_the_call_itself_is_never_changed_by_the_what_ifs():
    before = [t["text"] for t in quality.normalize([dict(t) for t in GOOD])[0]]
    r = quality.review([dict(t) for t in GOOD], "A.", "CALL-2")
    assert [t["text"] for t in r["turns"]] == before


def test_reviews_stored_before_the_explanation_get_it_when_read():
    r = quality.review(BAD, "A.", "CALL-1")
    old = {k: v for k, v in r.items() if k != "drivers"}
    old["errors"] = [{k: v for k, v in e.items() if k not in ("effect", "floored")} for e in old["errors"]]
    assert "drivers" not in quality_store._adjusted(old, None)              # the analytics never pay for it
    assert "drivers" in quality_store._shown(quality_store._adjusted(old, None), None)


def test_a_move_is_judged_on_its_own_sentences_not_the_whole_reply():
    mixed = [T("customer", 0, "I was charged twice on my September bill and this is the second time I call about it.", 32),
             T("advisor", 7, "Good morning, thank you for calling. I am sorry about the double charge, I understand how frustrating that is."),
             T("customer", 15, "Yes, please just fix it.", 40),
             T("advisor", 19, "Let me check the refund policy. The duplicate is 120 dinars, and I will refund it right away."),
             T("customer", 28, "Great, thanks.", 48)]
    helped = {d["rule"]: d for d in quality.review(mixed, "A.", "CALL-3")["drivers"]["helped"]}
    assert helped["check_first"]["effect"] > 0 and helped["check_first"]["prevents"] == ["Promise before the policy check"]   # same reply as the promise
    assert helped["empathy"]["effect"] > 0 and helped["greeting"]["effect"] > 0
