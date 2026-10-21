"""Quality analyst agent: scores a call transcript and says exactly where every lost point came from.

A call is a list of turns {speaker: 'advisor'|'customer', text, start, end, mood?, emotion?}. Scoring is rule based and explainable:
every rule finds a moment (a turn and its time), costs points in one criterion, and carries the fix that would have avoided it. So the
counterfactual ("if the policy had been checked first, compliance rises from 4 to 9") is exact, not a guess. An LLM judge would replace the
detectors, not this structure. The knowledge base (knowledge/base.json) is used twice: to check facts the advisor states, and to check that
the customer's problem was answered from it.

The criteria, each out of 10 (weights in WEIGHTS): Accuracy, Compliance, Communication, Resolution and Customer sentiment. The sentiment
criterion follows the customer's mood through the call; the mood comes from the emotion model when the call is audio, from the customer
simulator for live calls, and from a small word list when nothing better is given (then `moodSource` says "text").
"""
import math
import re

import advisor as kb
import customer

CRITERIA = ["Accuracy", "Compliance", "Communication", "Resolution", "Customer sentiment"]
WEIGHTS = {"Accuracy": 0.25, "Compliance": 0.25, "Communication": 0.20, "Resolution": 0.20, "Customer sentiment": 0.10}
MAX = 10
REFUND_LIMIT_TND = kb.REFUND_LIMIT_TND

MOVE_RX = dict(customer.READERS)      # the same readers the customer simulator uses: EMPATHY, CHECK_POLICY, PROMISE, FOLLOW_UP, ASK_REPEAT, TRANSFER

GREETING = re.compile(r"\b(hello|hi there|good (morning|afternoon|evening)|welcome|thank you for calling|speaking with|my name is)\b", re.I)
CLOSING = re.compile(r"\b(anything else|is there anything|thank you for calling|have a (good|great|nice)|glad (i|we) could help|pleasure)\b", re.I)
IDENTITY = re.compile(r"(\b(verify|confirm)\b.{0,30}\b(identity|name|date of birth|number|address|account)|date of birth|security (question|code)|\bid (card|number)\b)", re.I)
ACTION = re.compile(r"\b(refund\w*|credit\w*|reimburs\w*|cancel\w*|replac\w*|block\w*|activat\w*|waive\w*|change (your|the) plan)\b", re.I)
APPROVAL = re.compile(r"\b(supervisor|approval|approve\w*|authori[sz]\w*)\b", re.I)
RETENTION = re.compile(r"\b(review (your|the) (plan|contract)|better plan|another plan|offer|discount|keep you|stay with us|before (i|we) cancel)\b", re.I)
CANCEL_DONE = re.compile(r"\b(i('| wi)ll cancel|i have cancel\w*|cancel(l)?ed|i('| wi)ll (process|go ahead with) the cancellation|processing the cancellation)\b", re.I)
GUARANTEE = re.compile(r"\b(i guarantee|guaranteed|100 ?%|definitely will|will never happen|never happen again|absolutely sure|without a doubt)\b", re.I)
JARGON = re.compile(r"\b(apn|provisioning|msisdn|imsi|cdr|backend|tier ?2|ticket sla|crm|ivr|mnp|hlr)\b", re.I)
AMOUNT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:tnd|dinars?|dt)\b", re.I)
NEGATIVE = re.compile(r"\b(angry|furious|unacceptable|ridiculous|third time|again|never|terrible|useless|worst|unbelievable|fed up|disgust\w*|complain\w*|waiting|hanging up|cancel)\b", re.I)
POSITIVE = re.compile(r"\b(thank\w*|great|perfect|wonderful|appreciate\w*|brilliant|helpful|glad|happy)\b", re.I)
HANGUP = re.compile(r"\b(hanging up|goodbye|i'?m done|had enough)\b", re.I)
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10, "twenty-four": 24}

# facts the advisor may state, checked against the knowledge base: (rule id, context words, the value, why it is wrong, source)
FACTS = [
    dict(id="dispute_days", context=r"\b(dispute|contest)", value=r"\b(\d+|one|two|three|four|five|six|seven|ten)\s+(?:working\s+|business\s+)?days?\b",
         ok=lambda n, u: n == 5, says="an answer to a dispute is given within five working days", source="Dispute handling §2"),
    dict(id="restore_hours", context=r"\b(restor|reactivat|switched back on)\w*", value=r"\b(\d+|one|two|three|four|five|six|twenty-four)\s+(hours?|days?)\b",
         ok=lambda n, u: u.startswith("hour") and n == 1, says="the service is restored within one hour of the payment", source="Payments FAQ §2"),
    dict(id="plan_effective", context=r"\bplan\b.{0,40}\b(change|switch|upgrade|downgrade)|\b(change|switch|upgrade|downgrade)\b.{0,40}\bplan\b",
         value=r"\b(immediately|right away|straight away|today|right now|at once)\b", ok=lambda *_: False, says="a plan change takes effect on the next billing cycle", source="Plan change guide §1"),
    dict(id="refund_timing", context=r"\brefund.{0,60}\b(appear|show|in your account|credited|reach|statement)", value=r"\b(appears? )?(immediately|right away|straight away|today|right now)\b", ok=lambda *_: False,
         says="the refund appears on the next statement", source="Billing policy §4.2"),
    dict(id="sim_number", context=r"\bsim\b", value=r"\b(new number|different number|change your number)\b", ok=lambda *_: False,
         says="a replacement SIM keeps the same number", source="SIM and devices FAQ §1"),
]

# what each rule teaches and a training scenario to practise it (the Training agent will take these over); `cause` feeds the root-cause view
RULES = {
    "promise_before_check": dict(criterion="Compliance", points=5, cause="Process skipped", fix="the refund policy and approval had been checked first",
                                 tip="Check the policy before promising anything: say 'let me check the policy first', then confirm.", scenario="Double charge, customer asks for an immediate refund"),
    "refund_over_limit": dict(criterion="Compliance", points=4, cause="Process skipped", fix="a supervisor's approval had been asked for the amount above the limit",
                              tip=f"Refunds above {REFUND_LIMIT_TND} TND need a supervisor: name the approval step instead of promising the amount.", scenario="Large refund request, approval needed"),
    "no_identity_check": dict(criterion="Compliance", points=3, cause="Process skipped", fix="the customer's identity had been verified before the account action",
                              tip="Verify identity (name, date of birth) before any refund, cancellation or SIM change.", scenario="SIM replacement with identity verification"),
    "no_retention_offer": dict(criterion="Compliance", points=2, cause="Process skipped", fix="a plan review had been offered before processing the cancellation",
                               tip="Before processing a cancellation, offer a plan review: it is the retention step of the contract rules.", scenario="Cancellation with an early termination fee"),
    "wrong_fact": dict(criterion="Accuracy", points=4, cause="Knowledge gap", fix="the policy had been quoted correctly",
                       tip="Quote the knowledge base: the assistant shows the passage and its source for each answer.", scenario="Billing policy quiz: refunds, disputes and timing"),
    "no_grounded_answer": dict(criterion="Accuracy", points=3, cause="Knowledge gap", fix="the answer had been taken from the knowledge base",
                               tip="Search the knowledge base for the customer's problem and answer from the passage it returns.", scenario="Finding the right passage under pressure"),
    "overpromise": dict(criterion="Accuracy", points=2, cause="Soft skills", fix="the absolute guarantee had been avoided",
                        tip="Avoid 'guarantee' and '100 %': say what you will do and by when.", scenario="Customer threatens to post online"),
    "no_empathy": dict(criterion="Communication", points=3, cause="Soft skills", fix="the frustration had been acknowledged in the first reply",
                       tip="Acknowledge the frustration in the first reply, then explain what you will do.", scenario="Angry premium customer, third contact"),
    "jargon": dict(criterion="Communication", points=1, cause="Soft skills", fix="plain words had been used instead of technical terms",
                   tip="Replace technical terms by plain words, especially with new subscribers.", scenario="First call from a new subscriber about data limits"),
    "ask_repeat": dict(criterion="Communication", points=3, cause="Tools", fix="the customer's history on screen had been used instead of asking again",
                       tip="Read the customer's history first: asking them to repeat is the main cause of frustration.", scenario="Repeat contact, history already on file"),
    "transfer": dict(criterion="Communication", points=2, cause="Process skipped", fix="the call had been handled without a transfer (or the history handed over)",
                     tip="Handle it yourself when you can; if a transfer is needed, stay on the line and pass the full history.", scenario="Premium customer, two intents, transferred once"),
    "no_greeting": dict(criterion="Communication", points=1, cause="Soft skills", fix="the call had started with a greeting",
                        tip="Open with a greeting and offer help.", scenario="Opening a call well"),
    "no_follow_up": dict(criterion="Resolution", points=3, cause="Process skipped", fix="a written confirmation or ticket reference had been given",
                         tip="End with a written confirmation or a ticket number and say when the customer will hear back.", scenario="Closing a dispute with a follow-up"),
    "unresolved": dict(criterion="Resolution", points=4, cause="Knowledge gap", fix="the problem had been solved before the end of the call",
                       tip="Do not close while the customer is still unhappy: restate what is solved and what is next.", scenario="Customer still upset at the end of the call"),
    "hang_up": dict(criterion="Resolution", points=2, cause="Soft skills", fix="the customer had not hung up",
                    tip="Watch the patience signals: a customer who sounds done needs action, not more questions.", scenario="Impatient customer, short fuse"),
    "no_closing": dict(criterion="Resolution", points=1, cause="Soft skills", fix="the call had ended with a closing question",
                       tip="Close with 'is there anything else I can help with?'.", scenario="Opening a call well"),
    "mood_drop": dict(criterion="Customer sentiment", points=2, cause="Soft skills", fix="that reply had not made the customer's mood fall",
                      tip="After a drop in mood, acknowledge the feeling before the next step.", scenario="Customer becoming frustrated mid-call"),
    "low_mood_end": dict(criterion="Customer sentiment", points=0, cause="Soft skills", fix="the customer had left in a better mood",
                         tip="Finish on something concrete the customer can look forward to.", scenario="Customer still upset at the end of the call"),
}
RULE_LABELS = {
    "promise_before_check": "Promise before the policy check", "refund_over_limit": "Refund above the limit without approval", "no_identity_check": "No identity check",
    "no_retention_offer": "No retention offer before cancelling", "wrong_fact": "Fact contradicts the knowledge base", "no_grounded_answer": "Problem not answered from the knowledge base",
    "overpromise": "Absolute guarantee", "no_empathy": "No empathy for an upset customer", "jargon": "Technical jargon", "ask_repeat": "Customer asked to repeat",
    "transfer": "Transfer without the history", "no_greeting": "No greeting", "no_follow_up": "No written confirmation or follow-up", "unresolved": "Customer still upset at the end",
    "hang_up": "Customer hung up", "no_closing": "No closing question", "mood_drop": "Customer's mood fell after a reply", "low_mood_end": "Customer left in a low mood",
}
POSITIVES = {
    "empathy": "Acknowledged the customer's feelings", "check_first": "Checked the policy before promising", "identity": "Verified the customer's identity",
    "follow_up": "Gave a written confirmation or follow-up", "closing": "Closed the call properly", "greeting": "Greeted the customer", "mood_up": "The customer's mood rose",
}


def mmss(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _clip(text: str, n: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def normalize(turns: list[dict]) -> tuple[list[dict], str]:
    """Fill in times (estimated from the length of each turn when missing) and the customer's mood (from a word list when missing)."""
    out, t, given = [], 0.0, True
    for raw in turns:
        text = " ".join(str(raw["text"]).split())
        start = float(raw["start"]) if raw.get("start") is not None else t
        end = float(raw["end"]) if raw.get("end") is not None else start + 1.5 + len(text) / 14
        turn = dict(speaker=raw["speaker"], text=text, start=round(start, 1), end=round(end, 1), mood=raw.get("mood"), emotion=raw.get("emotion"))
        if turn["speaker"] == "customer" and turn["mood"] is None:
            given = False
            turn["mood"] = max(5, min(95, 55 - 12 * len(NEGATIVE.findall(text)) + 12 * len(POSITIVE.findall(text))))
        out.append(turn)
        t = end + 1.0
    return out, ("given" if given else "text")


def _finding(rule: str, idx: int, reason: str, turns: list[dict], points: int | None = None) -> dict:
    r = RULES[rule]
    return dict(rule=rule, criterion=r["criterion"], points=r["points"] if points is None else points, turn=idx, timestamp=mmss(turns[idx]["start"]),
                quote=_clip(turns[idx]["text"]), reason=reason, fix=r["fix"], cause=r["cause"])


def find_issues(turns: list[dict], intent_text: str, outcome: dict | None) -> tuple[list[dict], list[dict]]:
    """All the findings (points lost) and strengths in one call."""
    adv = [i for i, t in enumerate(turns) if t["speaker"] == "advisor"]
    cus = [i for i, t in enumerate(turns) if t["speaker"] == "customer"]
    issues: list[dict] = []
    good: list[dict] = []
    if not adv:
        return [dict(rule="unresolved", criterion=c, points=MAX, turn=0, timestamp="00:00", quote="", reason="The advisor never answered", fix="the advisor had answered", cause="Process skipped")
                for c in CRITERIA], good

    def at(rule, i, text):
        good.append(dict(rule=rule, turn=i, timestamp=mmss(turns[i]["start"]), text=text))

    # ---- compliance
    checked = identity = approval = False
    seen_check_at = None
    for i in adv:
        text = turns[i]["text"]
        if MOVE_RX["CHECK_POLICY"].search(text):
            if seen_check_at is None:
                seen_check_at = i
            checked = True
        if IDENTITY.search(text):
            if not identity:
                at("identity", i, POSITIVES["identity"])
            identity = True
        if APPROVAL.search(text):
            approval = True
        if MOVE_RX["PROMISE"].search(text) and not checked and not any(f["rule"] == "promise_before_check" for f in issues):
            issues.append(_finding("promise_before_check", i, "Promised a refund before checking the approval policy", turns))
        for m in AMOUNT.finditer(text):
            if float(m.group(1).replace(",", ".")) > REFUND_LIMIT_TND and ACTION.search(text) and not approval and not any(f["rule"] == "refund_over_limit" for f in issues):
                issues.append(_finding("refund_over_limit", i, f"Offered {m.group(0)} without a supervisor's approval (the limit is {REFUND_LIMIT_TND} TND)", turns))
        if ACTION.search(text) and not identity and not any(f["rule"] == "no_identity_check" for f in issues) and not re.search(r"\b(can|could|may) i\b", text, re.I) and not MOVE_RX["CHECK_POLICY"].search(text):
            issues.append(_finding("no_identity_check", i, "Acted on the account before verifying the customer's identity", turns))
    if seen_check_at is not None and not any(f["rule"] == "promise_before_check" for f in issues):
        at("check_first", seen_check_at, POSITIVES["check_first"])
    if re.search(r"\b(cancel|terminate)", intent_text, re.I):
        for i in adv:
            if CANCEL_DONE.search(turns[i]["text"]) and not any(RETENTION.search(turns[j]["text"]) for j in adv if j <= i):
                issues.append(_finding("no_retention_offer", i, "Processed the cancellation without offering a plan review first", turns))
                break

    # ---- accuracy: facts against the knowledge base, a grounded answer, absolute guarantees
    wrong = 0
    for i in adv:
        for f in FACTS:
            text = turns[i]["text"]
            if wrong < 2 and re.search(f["context"], text, re.I):
                m = re.search(f["value"], text, re.I)
                if m:
                    n = None
                    u = ""
                    groups = [g for g in m.groups() if g]
                    if groups and (groups[0].isdigit() or groups[0].lower() in WORDS):
                        n = int(groups[0]) if groups[0].isdigit() else WORDS[groups[0].lower()]
                        u = groups[1].lower() if len(groups) > 1 else ""
                    if not f["ok"](n, u):
                        issues.append(_finding("wrong_fact", i, f"Stated something the knowledge base contradicts: {f['source']} says {f['says']}", turns))
                        wrong += 1
                        break
        if GUARANTEE.search(turns[i]["text"]) and not any(f["rule"] == "overpromise" for f in issues):
            issues.append(_finding("overpromise", i, "Gave an absolute guarantee the advisor cannot be sure of", turns))
    if cus:
        passage, _ = kb.retrieve(intent_text, 1)[0]
        best = max((kb.cosine(turns[i]["text"], f"{passage['title']}. {passage['text']}") for i in adv), default=0.0)
        if best < 0.10 and kb.retrieve(intent_text, 1)[0][1] >= kb.MIN_SCORE:
            issues.append(_finding("no_grounded_answer", adv[0], f"None of the advisor's replies covers the knowledge-base answer ({passage['source']}: {passage['title'].lower()})", turns))

    # ---- communication
    first_c = turns[cus[0]] if cus else None
    if first_c and (first_c["mood"] < 45 or first_c.get("emotion") in ("anger", "sad", "fear", "disgust")):
        early = adv[:2]
        if not any(MOVE_RX["EMPATHY"].search(turns[i]["text"]) for i in early):
            issues.append(_finding("no_empathy", early[0], "The customer was upset and the first replies did not acknowledge it", turns))
        else:
            i = next(i for i in early if MOVE_RX["EMPATHY"].search(turns[i]["text"]))
            at("empathy", i, POSITIVES["empathy"] + " before moving on")
    elif any(MOVE_RX["EMPATHY"].search(turns[i]["text"]) for i in adv):
        i = next(i for i in adv if MOVE_RX["EMPATHY"].search(turns[i]["text"]))
        at("empathy", i, POSITIVES["empathy"])
    jargon_seen = set()
    for i in adv:
        for m in JARGON.finditer(turns[i]["text"]):
            if m.group(0).lower() not in jargon_seen and len(jargon_seen) < 2:
                jargon_seen.add(m.group(0).lower())
                issues.append(_finding("jargon", i, f"Used the technical term '{m.group(0)}' with a customer", turns))
    for rule, key, limit in (("ask_repeat", "ASK_REPEAT", 2), ("transfer", "TRANSFER", 2)):
        n = 0
        for i in adv:
            if MOVE_RX[key].search(turns[i]["text"]) and n < limit:
                n += 1
                reason = "Asked the customer to explain the problem again" if rule == "ask_repeat" else (
                    "Transferred the customer" + ("" if re.search(r"\b(history|stay on the line|summary|brief)", turns[i]["text"], re.I) else " without passing the history"))
                if rule == "transfer" and "without" not in reason:
                    continue
                issues.append(_finding(rule, i, reason, turns))
    if not GREETING.search(turns[adv[0]]["text"]):
        issues.append(_finding("no_greeting", adv[0], "The call did not start with a greeting", turns))
    else:
        at("greeting", adv[0], POSITIVES["greeting"])

    # ---- resolution
    follow = [i for i in adv if MOVE_RX["FOLLOW_UP"].search(turns[i]["text"])]
    if not follow:
        issues.append(_finding("no_follow_up", adv[-1], "No written confirmation, ticket reference or follow-up was given", turns))
    else:
        at("follow_up", follow[0], POSITIVES["follow_up"])
    last_c = turns[cus[-1]] if cus else None
    hung = bool(outcome and outcome.get("verdict", "").startswith("The client hung up")) or bool(last_c and HANGUP.search(last_c["text"]) and last_c["mood"] < 40)
    if hung and cus:
        issues.append(_finding("hang_up", cus[-1], "The customer hung up", turns))
    if last_c and last_c["mood"] < 40 and not follow:
        issues.append(_finding("unresolved", cus[-1], f"The customer ended the call still upset (mood {last_c['mood']}/100) with nothing agreed", turns))
    elif outcome and outcome.get("verdict") == "Call left open." and not follow:
        pass
    if CLOSING.search(turns[adv[-1]]["text"]):
        at("closing", adv[-1], POSITIVES["closing"])
    else:
        issues.append(_finding("no_closing", adv[-1], "The call ended without a closing question", turns))

    # ---- customer sentiment: where the mood fell, and where it ended
    moods = [(i, turns[i]["mood"]) for i in cus]
    drops = 0
    for (i0, m0), (i1, m1) in zip(moods, moods[1:]):
        prior = [a for a in adv if i0 < a < i1]
        if m0 - m1 >= 15 and prior and drops < 2:
            drops += 1
            issues.append(_finding("mood_drop", prior[-1], f"The customer's mood fell from {m0} to {m1} after this reply", turns))
        if m1 - m0 >= 15 and prior and not any(g["rule"] == "mood_up" for g in good):
            at("mood_up", prior[-1], f"{POSITIVES['mood_up']} from {m0} to {m1} after this reply")
    if moods:
        end_mood = moods[-1][1]
        loss = max(0, round((70 - end_mood) / 10))
        if loss:
            f = _finding("low_mood_end", moods[-1][0], f"The customer left in a mood of {end_mood}/100", turns, points=loss)
            issues.append(f)
    return issues, good


def score(issues: list[dict]) -> dict[str, int]:
    return {c: max(0, MAX - sum(f["points"] for f in issues if f["criterion"] == c)) for c in CRITERIA}


def overall(scores: dict[str, int]) -> int:
    return round(100 * sum(WEIGHTS[c] * scores[c] / MAX for c in CRITERIA))


def counterfactual(issues: list[dict], scores: dict[str, int]) -> str:
    """The single fix with the biggest effect on the overall score, worked out by really removing that finding."""
    if not issues:
        return "No point was lost: keep doing what this call did."
    base = overall(scores)
    best = None
    for f in issues:
        rest = [x for x in issues if x is not f]
        s2 = score(rest)
        gain = overall(s2) - base
        if best is None or gain > best[0]:
            best = (gain, f, s2)
    gain, f, s2 = best
    return (f"If {f['fix']} (at {f['timestamp']}), {f['criterion'].lower()} would rise from {scores[f['criterion']]} to {s2[f['criterion']]} "
            f"and the overall score by {gain:+d}.")


def review(turns: list[dict], advisor_name: str, call_id: str, source: str = "api", outcome: dict | None = None, date: str | None = None) -> dict:
    """Score a call. Returns the contract's QualityReview plus the transcript, errors, strengths and coaching."""
    turns, mood_source = normalize(turns)
    if not any(t["speaker"] == "advisor" for t in turns) and not turns:
        raise ValueError("The call has no turns.")
    first_c = next((t["text"] for t in turns if t["speaker"] == "customer"), turns[0]["text"])
    issues, good = find_issues(turns, first_c, outcome)
    scores = score(issues)
    criteria = []
    for c in CRITERIA:
        mine = sorted((f for f in issues if f["criterion"] == c), key=lambda f: -f["points"])
        if mine:
            evidence = mine[0]["reason"] + (f" (+{len(mine) - 1} more)" if len(mine) > 1 else "")
            ts = mine[0]["timestamp"]
        else:
            pos = [g for g in good if g["rule"] in {"Accuracy": (), "Compliance": ("check_first", "identity"), "Communication": ("empathy", "greeting"),
                                                    "Resolution": ("follow_up", "closing"), "Customer sentiment": ("mood_up",)}[c]]
            evidence = pos[0]["text"] if pos else "No error found"
            ts = pos[0]["timestamp"] if pos else "00:00"
        criteria.append(dict(name=c, score=scores[c], max=MAX, evidence=evidence, timestamp=ts))
    flags: dict[int, list[str]] = {}
    for f in issues:
        flags.setdefault(f["turn"], []).append(f["rule"])
    for g in good:
        flags.setdefault(g["turn"], []).append("+" + g["rule"])
    for i, t in enumerate(turns):
        t["flags"] = flags.get(i, [])
    coaching, seen = [], set()
    for f in sorted(issues, key=lambda f: -f["points"]):
        if f["rule"] not in seen and f["points"] > 0:
            seen.add(f["rule"])
            coaching.append(dict(rule=f["rule"], criterion=f["criterion"], tip=RULES[f["rule"]]["tip"], scenario=RULES[f["rule"]]["scenario"]))
    intents = kb.detect_intents(first_c)
    return dict(
        callId=call_id, advisor=advisor_name, overall=overall(scores), criteria=criteria, counterfactual=counterfactual(issues, scores),
        source=source, date=date, durationSec=round(turns[-1]["end"]), intent=intents[0] if intents else "Other", moodSource=mood_source,
        errors=sorted(({k: v for k, v in f.items()} for f in issues), key=lambda f: (-f["points"], f["turn"])),
        strengths=[dict(timestamp=g["timestamp"], text=g["text"], rule=g["rule"]) for g in good], coaching=coaching, turns=turns,
        moodCurve=[[t["start"], t["mood"]] for t in turns if t["speaker"] == "customer"],
    )
