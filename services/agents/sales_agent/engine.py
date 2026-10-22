"""The sales agent's brain: spot what a customer needs (in the conversation, or in their file) and rank the offers that answer it.

Every relevance score is a sum of named factors, each with its points and the reason in words, so Leila (and the teacher) can see exactly why an
offer is suggested and what would change it:
  what the customer said   up to 50   the need, with the customer's own words
  fit with the contract    15         the offer is not already covered or owned
  customer value           up to 15   years with us, premium plan, a customer at risk for a retention offer
  the moment               -20 to +10 mood and open tickets: do not sell to someone who is upset, solve first
  track record             -10 to +10 how often this offer was accepted before (a smoothed rate)
The needs are found with phrase patterns on what the customer said, not with a language model, and the offers, prices and customers are invented.
"""
import json
import re
from pathlib import Path

import advisor

_K = Path(__file__).resolve().parents[1] / "knowledge"
CATALOG = json.loads((_K / "offers.json").read_text(encoding="utf-8"))
PROFILES = {k: v for k, v in json.loads((_K / "sales_profiles.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
OFFERS = {o["id"]: o for o in CATALOG["offers"]}
NEEDS = {k: dict(label=v["label"], rx=re.compile(v["rx"], re.I)) for k, v in CATALOG["needs"].items()}

MOOD_OF = {"Calm": 70, "Curious": 65, "Impatient": 45, "Frustrated": 30, "Angry": 20}
NEGATIVE = re.compile(r"\b(angry|furious|unacceptable|terrible|awful|fed up|ridiculous|third time|unhappy|useless|disgusting|sick of)\b", re.I)
POSITIVE = re.compile(r"\b(thanks|thank you|great|perfect|happy|glad|wonderful|that helps|sounds good)\b", re.I)
NEGATED = re.compile(r"\b(don't|do not|doesn't|never|won't|no intention|no plan|not want to|not (going|planning|thinking|leaving|cancel(l)?ing|switching)|(i'?m|i am|am) not)\b", re.I)
NEGATABLE = {"leaving", "travel", "device", "family", "premium_service"}      # "I'm not leaving" must not count as leaving
SPLIT = re.compile(r"(?<=[.!?;])\s+")


def mmss(seconds: float) -> str:
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def conversation_needs(turns: list[dict]) -> dict[str, dict]:
    """The needs the customer voiced: need key -> label, the first quote with its time, how many replies mention it, and a strength 0 to 1."""
    found: dict[str, dict] = {}
    for i, t in enumerate(turns):
        if t["speaker"] != "customer":
            continue
        for sentence in SPLIT.split(t["text"]):
            for key, need in NEEDS.items():
                if need["rx"].search(sentence) and not (key in NEGATABLE and NEGATED.search(sentence)):
                    n = found.setdefault(key, dict(label=need["label"], quote=sentence.strip(), turn=i, time=mmss(t["start"]) if t.get("start") is not None else None,
                                                   turns=set(), source="conversation"))
                    n["turns"].add(i)
    for n in found.values():
        n["mentions"] = len(n.pop("turns"))
        n["strength"] = min(1.0, 0.7 + 0.15 * (n["mentions"] - 1))
    return found


def file_needs(customer: dict | None) -> dict[str, dict]:
    """What the customer's file suggests: the reasons of the contacts, and usage dropping. Weaker than something said out loud."""
    if not customer:
        return {}
    out: dict[str, dict] = {}
    for intent in customer["intents"]:
        link = CATALOG["intent_needs"].get(intent)
        if link:
            out.setdefault(link[0], dict(label=NEEDS[link[0]]["label"], quote=f"Contacted us about: {intent.lower()}", turn=None, time=None, mentions=1, strength=link[1], source="file"))
    trend = PROFILES.get(customer["id"], {}).get("usageTrend", 0)
    if trend <= -30:
        out["leaving"] = dict(label="Thinking of leaving", quote=f"Usage down {abs(trend)}% in two months", turn=None, time=None, mentions=1, strength=max(0.6, out.get("leaving", {}).get("strength", 0)), source="file")
    return out


def merge_needs(spoken: dict, filed: dict) -> dict:
    merged = dict(filed)
    for k, v in spoken.items():
        if k not in merged or v["strength"] >= merged[k]["strength"]:
            merged[k] = v
    return merged


def mood_of(turns: list[dict], customer: dict | None) -> int:
    """The customer's latest mood: the one given with their last reply, else guessed from their words, else from their file."""
    spoken = [t for t in turns if t["speaker"] == "customer"]
    if spoken and spoken[-1].get("mood") is not None:
        return int(spoken[-1]["mood"])
    text = " ".join(t["text"] for t in spoken[-2:])
    if NEGATIVE.search(text):
        return 30
    if POSITIVE.search(text):
        return 65
    return MOOD_OF.get(customer["mood"], 55) if customer else 55


def offer_name(offer: dict, plan: str) -> str | None:
    if offer["id"] != "plan-upgrade":
        return offer["name"]
    nxt = CATALOG["upgrade_path"].get(plan)
    return f"Upgrade to {nxt}" if nxt else None


def recommend(customer: dict | None, needs: dict, mood: int, rates: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Ranked offers (most relevant first) and the offers set aside with the reason."""
    plan = customer["contract"] if customer else ""
    profile = PROFILES.get(customer["id"], {}) if customer else {}
    tickets = customer["openTickets"] if customer else 0
    tenure, trend = profile.get("tenureYears"), profile.get("usageTrend", 0)
    ranked, skipped = [], []
    for o in CATALOG["offers"]:
        links = sorted(((needs[k]["strength"] * w, k) for k, w in o["needs"].items() if k in needs), reverse=True)
        if not links:
            continue
        name = offer_name(o, plan)
        if name is None or any(p in plan for p in o["excluded_plans"]):
            skipped.append(dict(offerId=o["id"], offer=o["name"], why=f"{plan} already covers it" if plan else "not available"))
            continue
        if o["id"] in profile.get("addons", []):
            skipped.append(dict(offerId=o["id"], offer=o["name"], why="the customer already has it"))
            continue
        if tenure is not None and tenure < o.get("min_tenure_years", 0):
            skipped.append(dict(offerId=o["id"], offer=o["name"], why=f"needs {o['min_tenure_years']:g} year of tenure, the customer has {tenure:g}"))
            continue
        combo = min(1.0, links[0][0] + 0.25 * sum(v for v, _ in links[1:]))
        top = needs[links[0][1]]
        said = f"“{top['quote']}”" + (f" at {top['time']}" if top["time"] else "") if top["source"] == "conversation" else top["quote"]
        factors = [dict(name="What the customer said" if top["source"] == "conversation" else "What the file says", points=round(50 * combo),
                        why=f"{said}: {top['label'].lower()}")]
        factors.append(dict(name="Fit with the contract", points=15, why=f"{plan or 'no contract on file'}: not already covered"))
        value, why = 0, []
        if tenure and tenure >= 5:
            value, why = value + 10, why + [f"{tenure:g} years with us"]
        elif tenure and tenure >= 2:
            value, why = value + 5, why + [f"{tenure:g} years with us"]
        if "Premium" in plan:
            value, why = value + 5, why + ["premium plan"]
        if o["kind"] == "retention" and trend <= -30:
            value, why = value + 15, why + [f"usage down {abs(trend)}%: worth keeping"]
        if value:
            factors.append(dict(name="Customer value", points=min(15, value), why=", ".join(why)))
        retention = o["kind"] == "retention"
        if retention and mood < 40:
            moment, mwhy = 5, f"mood {mood}: a retention offer suits an upset customer, after acknowledging the problem"
        elif mood < 40:
            moment, mwhy = -20, f"mood {mood}: solve the problem before selling"
        elif tickets and not retention:
            moment, mwhy = -10, f"{tickets} open ticket{'s' if tickets > 1 else ''}: solve {'it' if tickets == 1 else 'them'} first"
        elif mood >= 60:
            moment, mwhy = 10, f"mood {mood}: a relaxed moment"
        else:
            moment, mwhy = 0, f"mood {mood}: neutral"
        if moment:
            factors.append(dict(name="The moment", points=moment, why=mwhy))
        if rates and o["id"] in rates:
            offered, accepted = rates[o["id"]]
            rate = (accepted + 2) / (offered + 4)
            record = max(-10, min(10, round(20 * (rate - 0.5))))
            if record:
                factors.append(dict(name="Track record", points=record, why=f"accepted {round(100 * rate)}% of the time in the history (simulated)"))
        total = max(0, min(100, sum(f["points"] for f in factors)))
        worst = min((f for f in factors if f["points"] < 0), key=lambda f: f["points"], default=None)
        ranked.append(dict(
            offerId=o["id"], offer=name, price=o["price"], kind=o["kind"], pitch=o["pitch"], relevance=total, reason=said,
            need=dict(key=links[0][1], label=top["label"]), factors=factors,
            timing=dict(cue="after_resolution" if moment < 0 else "now", why=mwhy),
            counterfactual=f"Without “{worst['name']}” ({worst['why']}), the relevance would be {total - worst['points']}." if worst else None))
    ranked.sort(key=lambda r: -r["relevance"])
    return ranked, skipped


def detect(turns: list[dict], customer_id: str | None, rates: dict | None = None, top: int = 4) -> dict:
    """The needs voiced in a conversation (plus what the customer's file says) and the offers that answer them, with the reasons."""
    customer = advisor.get_customer(customer_id) if customer_id else None
    spoken = conversation_needs(turns)
    needs = merge_needs(spoken, file_needs(customer))
    mood = mood_of(turns, customer)
    offers, skipped = recommend(customer, needs, mood, rates)
    signals = sorted(({k: v for k, v in dict(need=k, **n).items() if k != "strength"} | dict(strength=round(n["strength"], 2)) for k, n in needs.items()),
                     key=lambda s: -s["strength"])
    return dict(customerId=customer_id, customer=customer["name"] if customer else None, mood=mood, signals=signals, offers=offers[:top], skipped=skipped)


def opportunities(rates: dict | None = None) -> list[dict]:
    """One line per customer on file: the best offer for them today (what their file says, no conversation), with its reasons."""
    out = []
    for c in advisor.CUSTOMERS:
        offers, _ = recommend(c, file_needs(c), MOOD_OF.get(c["mood"], 55), rates)
        if offers:
            best = offers[0]
            out.append(dict(best, customer=c["name"], customerId=c["id"], alternatives=[dict(offer=o["offer"], relevance=o["relevance"]) for o in offers[1:3]]))
    return sorted(out, key=lambda o: -o["relevance"])
