"""The advisor agent: its plan reads the call, its words are checked, and it still works without the language model."""
import advisor_agent as agent
import customer
import local_llm
from quality_analyst import engine as quality

OPENING = "I was charged twice on my September bill."


def _call(persona, difficulty, intent, opening=None):
    """The advisor agent talks to the customer simulator until the call ends. Returns the steps, the moves, and the review."""
    s = customer.start(persona, None, difficulty, intent, False, opening)
    turns, steps, moves = [dict(speaker="customer", text=s["opening"], mood=s["mood"])], [], []
    for turn in range(customer.MAX_MOVES):
        r = agent.reply(s["opening"], turn, turns, steps)
        assert 10 <= len(r["text"]) <= agent.MAX_CHARS and r["why"] and r["engine"]
        steps.append(r["step"])
        turns.append(dict(speaker="advisor", text=r["text"]))
        said = customer.say(s["id"], r["text"])
        moves.append(said["move"])
        if said["client"]:
            turns.append(dict(speaker="customer", text=said["client"], mood=said["mood"]))
        if said["ended"]:
            break
    done, outcome, _ = customer.transcript(s["id"])
    return steps, moves, outcome, quality.review(done, "Agent", "CALL-1", outcome=outcome, with_drivers=False)


def test_without_the_model_every_call_is_resolved_in_fixed_wording_and_scores_well():
    for persona in customer.PERSONAS:
        for difficulty in ("MEDIUM", "HARD"):
            for intent in customer.INTENTS:
                steps, moves, outcome, review = _call(persona, difficulty, intent)
                assert steps[0] == "acknowledge" and steps[-1] == "follow up in writing", steps
                assert moves[0] == "EMPATHY" and moves[1] == "CHECK_POLICY" and moves[-1] == "FOLLOW_UP", moves
                assert outcome["verdict"].startswith("Resolved"), (persona, difficulty, intent, outcome)
                assert review["overall"] >= 90, (persona, difficulty, intent, review["overall"], [e["rule"] for e in review["errors"]])


def test_a_falling_mood_is_answered_before_the_process_goes_on():
    turns = [dict(speaker="customer", text=OPENING, mood=50), dict(speaker="advisor", text="Hello, I am sorry."), dict(speaker="customer", text="That is useless!", mood=38)]
    step, why = agent.plan(turns, ["acknowledge"], 1)
    assert step == agent.CALM and "from 50 to 38" in why
    turns += [dict(speaker="advisor", text="I hear you."), dict(speaker="customer", text="Fine.", mood=30)]
    assert agent.plan(turns, ["acknowledge", agent.CALM], 2)[0] == "check the policy", "calming twice in a row would not move the call on"


def test_the_plan_keeps_room_for_the_four_steps():
    upset = [dict(speaker="customer", text=OPENING, mood=50), dict(speaker="customer", text="No!", mood=20)]
    steps = ["acknowledge", agent.CALM, "check the policy", agent.ANSWER, agent.CALM]
    assert agent.plan(upset, steps, 5)[0] == "give the solution", "with one reply left the call cannot spend it on calming"


def test_only_a_real_question_after_the_solution_gets_its_own_answer():
    done = ["acknowledge", "check the policy", "give the solution"]
    asked = [dict(speaker="customer", text=OPENING, mood=50), dict(speaker="customer", text="When will it reach my account?", mood=52)]
    assert agent.plan(asked, done, 3)[0] == agent.ANSWER
    go_on = [dict(speaker="customer", text=OPENING, mood=50), dict(speaker="customer", text="Hm, okay. And then?", mood=52)]
    assert agent.plan(go_on, done, 3)[0] == "follow up in writing"


def test_the_quality_rules_refuse_what_should_not_be_said():
    turns = [dict(speaker="customer", text=OPENING, mood=50)]
    known = OPENING
    assert any("before checking" in p for p in agent.check("I will refund you right away.", "give the solution", turns, known))
    assert any("guarantee" in p.lower() for p in agent.check("I guarantee this will never happen again, it is solved.", "give the solution", turns, known))
    assert any("transfer" in p.lower() for p in agent.check("Let me transfer you to the billing team.", "give the solution", turns, known))
    assert any("numbers" in p for p in agent.check("You will get 75 dinars back on the statement.", "give the solution", turns, known)), "a figure from nowhere"
    assert any("placeholders" in p for p in agent.check("Hello [customer name], welcome to our service line.", "give the solution", turns, known))
    assert any("email" in p for p in agent.check("I will send you a confirmation by email today.", "give the solution", turns, known)), "the customer would take it as the end of the call"
    assert agent.check("I'm sorry", "acknowledge", turns, known), "the first reply must also greet and verify"
    assert agent.check("The refund appears on your next statement.", "give the solution", turns + [dict(speaker="advisor", text="Let me check the refund policy, can you confirm your date of birth?")], known) == []


def test_a_good_draft_is_used_a_bad_one_gets_a_second_try_then_the_fixed_wording(monkeypatch):
    drafts = iter(["I guarantee this is solved for good.", "The duplicate is reviewed and the refund appears on your next statement."])
    asked = []
    monkeypatch.setattr(local_llm, "chat_json", lambda system, user, **k: asked.append(user) or dict(reply=next(drafts)))
    turns = [dict(speaker="customer", text=OPENING, mood=50), dict(speaker="advisor", text="Let me check the refund policy, can you confirm your date of birth?")]
    r = agent.reply(OPENING, 2, turns, ["acknowledge", "check the policy"])
    assert r["engine"].startswith("local model") and r["text"].startswith("The duplicate") and "second try" in r["checks"][0]
    assert "refused_draft" in asked[1] and "refused_draft" not in asked[0]

    monkeypatch.setattr(local_llm, "chat_json", lambda system, user, **k: dict(reply="I guarantee it, 100 % solved."))
    r = agent.reply(OPENING, 0, [dict(speaker="customer", text=OPENING, mood=50)], [])
    assert r["engine"] == "fixed wording" and "refused" in r["checks"][0] and "date of birth" in r["text"]


def test_no_model_answer_means_fixed_wording_and_it_says_so(monkeypatch):
    monkeypatch.setattr(local_llm, "chat_json", lambda *a, **k: None)
    r = agent.reply(OPENING, 0, [dict(speaker="customer", text=OPENING, mood=50)], [])
    assert r["engine"] == "fixed wording" and "did not answer" in r["checks"][0]


def test_the_passage_reaches_the_model_and_an_unknown_problem_promises_nothing(monkeypatch):
    seen = []
    monkeypatch.setattr(local_llm, "chat_json", lambda system, user, **k: seen.append(user))
    agent.reply(OPENING, 2, [dict(speaker="customer", text=OPENING, mood=50)], ["acknowledge", "check the policy"], brief="A repeat caller.")
    assert "Billing policy" in seen[0] and "A repeat caller." in seen[0]
    r = agent.reply("xyzzy plugh", 2, [dict(speaker="customer", text="xyzzy plugh", mood=50)], ["acknowledge", "check the policy"])
    assert "No passage matches" in seen[1] and not r["sources"]


def test_a_rushed_advisor_stays_a_fixed_script():
    r = agent.reply(OPENING, 0, style="rushed")
    assert r["step"] == "promise too early" and r["engine"] == "fixed script"


def test_local_llm_is_off_in_the_tests_and_answers_none():
    assert not local_llm.enabled() and local_llm.chat_json("s", "u") is None and not local_llm.available()
