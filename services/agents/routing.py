"""Routing and allocation: which advisor should work which queue for the rest of the day.

The method is a local search on the Erlang C numbers of workforce.py, not reinforcement learning. For each coming hour it starts from
today's roster (every advisor on their own queue) and repeatedly makes the single move of a cross-skilled advisor to another queue
that raises the objective most, until no move helps and no queue is pushed below 65 % service. The objective is the priority-weighted number of calls answered within 20 seconds,
sum over queues of priority x calls x service level(advisors). That function has diminishing returns, which is why a greedy search
finds a good allocation; every move is explained by the service levels before and after. A discrete-event simulation (Poisson calls,
exponential handling times, first come first served) then checks the gain independently of the formula.

Reinforcement learning is kept for later: it needs a calibrated simulator and real call logs, and it would be judged against this method.
The skills, advisors and priorities below are synthetic demo data.
"""
import heapq
from functools import lru_cache

import numpy as np

import workforce as wf

PRIORITY = {"A": 1.0, "B": 1.3, "C": 0.9, "D": 1.0, "E": 0.8}     # B is the premium queue: its calls count 30 % more
CROSS_SKILLS = {"A": ["B"], "B": ["A"], "C": ["D", "A"], "D": ["C", "E"], "E": ["D"]}
MAX_MOVES_PER_HOUR = 6
GUARD = 0.65                                                         # a queue never gives up an advisor if that drops it below 65 % (or below what it has now, when it is already lower)
MIN_GAIN = 0.05                                                      # a move must win at least this many weighted calls per hour


def advisors() -> list[dict]:
    """The synthetic advisor pool: queue letter + number, primary queue, and the queues each can also serve (every second one is cross-skilled)."""
    pool = []
    for q in wf.QUEUES:
        for i in range(max(wf.roster(q))):
            pool.append(dict(id=f"{q}{i + 1:02d}", primary=q, index=i, skills=[q] + (CROSS_SKILLS[q] if i % 2 == 1 else [])))
    return pool


def on_duty(hour: int) -> list[dict]:
    return [a for a in advisors() if a["index"] < wf.roster(a["primary"])[wf.HOURS.index(hour)]]


def objective(calls: dict, counts: dict) -> float:
    return sum(PRIORITY[q] * calls[q] * wf.stats(calls[q], wf.QUEUES[q]["aht"], counts[q])["sla"] for q in wf.QUEUES)


def _counts(assign: dict) -> dict:
    c = {q: 0 for q in wf.QUEUES}
    for q in assign.values():
        c[q] += 1
    return c


def allocate(hour: int) -> dict:
    """The plan for one hour: counts before and after per queue, and the ranked moves."""
    calls = {q: next(p["forecast"] for p in wf.forecast(q) if p["hour"] == f"{hour}h") for q in wf.QUEUES}
    duty = on_duty(hour)
    assign = {a["id"]: a["primary"] for a in duty}
    skills = {a["id"]: a["skills"] for a in duty}
    before = _counts(assign)
    floor = {q: min(GUARD, wf.stats(calls[q], wf.QUEUES[q]["aht"], before[q])["sla"]) for q in wf.QUEUES}
    moves = []
    for _ in range(MAX_MOVES_PER_HOUR):
        now = _counts(assign)
        base = objective(calls, now)
        best = None
        for adv, s in assign.items():
            for t in skills[adv]:
                if t == s:
                    continue
                trial = dict(now)
                trial[s] -= 1
                trial[t] += 1
                if wf.stats(calls[s], wf.QUEUES[s]["aht"], trial[s])["sla"] < floor[s] - 1e-9:
                    continue                                   # the donor queue would fall below its protected level
                gain = objective(calls, trial) - base
                if gain > MIN_GAIN and (best is None or gain > best[0]):
                    best = (gain, adv, s, t)
        if best is None:
            break
        gain, adv, s, t = best
        sla_before = {q: wf.stats(calls[q], wf.QUEUES[q]["aht"], now[q])["sla"] for q in (s, t)}
        assign[adv] = t
        after = _counts(assign)
        sla_after = {q: wf.stats(calls[q], wf.QUEUES[q]["aht"], after[q])["sla"] for q in (s, t)}
        moves.append(dict(
            advisor=adv, skills=skills[adv], fromQueue=s, toQueue=t, gain=round(gain, 1),
            text=(f"Move {adv} (skills {', '.join(skills[adv])}) from queue {s} to queue {t} at {hour}h: queue {t} goes from {sla_before[t]:.0%} to {sla_after[t]:.0%} "
                  f"within 20 s, queue {s} from {sla_before[s]:.0%} to {sla_after[s]:.0%}."),
        ))
    after = _counts(assign)
    rows = []
    for q in wf.QUEUES:
        aht, c = wf.QUEUES[q]["aht"], calls[q]
        b, a = wf.stats(c, aht, before[q]), wf.stats(c, aht, after[q])
        rows.append(dict(queue=q, name=wf.QUEUES[q]["name"], calls=c, priority=PRIORITY[q], advisors=before[q], recommended=after[q],
                         baselineSla=round(b["sla"], 2), recommendedSla=round(a["sla"], 2), baselineWaitSec=round(b["wait"]), recommendedWaitSec=round(a["wait"])))
    return dict(hour=f"{hour}h", queues=rows, moves=moves)


def simulate_hour(calls: float, aht: float, n: int, reps: int, seed: int) -> float:
    """Share of calls answered within 20 s in a discrete-event simulation: Poisson arrivals, exponential handling, first come first served.
    The first hour of each two-hour run is thrown away so the queue is in its usual state."""
    if calls <= 0:
        return 1.0
    if n <= 0:
        return 0.0
    rng = np.random.default_rng(seed)
    ok = total = 0
    for _ in range(reps):
        t, free = 0.0, [0.0] * n
        heapq.heapify(free)
        while True:
            t += rng.exponential(3600 / calls)
            if t >= 7200:
                break
            start = max(t, heapq.heappop(free))
            heapq.heappush(free, start + rng.exponential(aht))
            if t >= 3600:
                total += 1
                ok += start - t <= wf.TARGET_SECONDS
    return ok / total if total else 1.0


@lru_cache(maxsize=None)
def plan(check_reps: int = 60) -> dict:
    """The routing plan for the hours still to come today, with the simulation check. Deterministic, so cached."""
    hours = [allocate(h) for h in wf.HOURS if h > wf.NOW_HOUR]
    base_n = opt_n = base_ok = opt_ok = base_sim = opt_sim = 0.0
    for hr in hours:
        for r in hr["queues"]:
            c, aht = r["calls"], wf.QUEUES[r["queue"]]["aht"]
            base_n += c; base_ok += c * r["baselineSla"]; opt_ok += c * r["recommendedSla"]
            if check_reps:
                seed = int(hr["hour"][:-1]) * 100 + ord(r["queue"])
                base_sim += c * simulate_hour(c, aht, r["advisors"], check_reps, seed)
                opt_sim += c * simulate_hour(c, aht, r["recommended"], check_reps, seed)
    out = dict(
        baselineSla=round(base_ok / base_n, 2), optimizedSla=round(opt_ok / base_n, 2), moves=sum(len(h["moves"]) for h in hours), hours=hours,
        method=("Local search on Erlang C numbers: each advisor with the right skill moves to the queue where it wins the most priority-weighted calls "
                f"answered within {wf.TARGET_SECONDS} s. Priorities: " + ", ".join(f"{q} x{p}" for q, p in PRIORITY.items()) + ". Advisors and skills are synthetic."),
    )
    if check_reps:
        out["simulated"] = dict(baselineSla=round(base_sim / base_n, 2), optimizedSla=round(opt_sim / base_n, 2), replications=check_reps)
    return out
