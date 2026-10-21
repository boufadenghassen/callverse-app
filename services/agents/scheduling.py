"""Breaks and shifts: when should each advisor take lunch, and where is overtime needed?

For a typical day (the seasonal call profile of workforce.py) every advisor who works long enough takes one hour of lunch between 11h and 15h.
The naive plan sends everybody at 12h, which empties the queues at the busiest time. The planned version moves lunches one at a time to
the hour where it costs the fewest calls answered within 20 seconds, until no single change helps (local search on the Erlang C numbers).
What is still short after lunches becomes an overtime estimate. Advisors and shifts are synthetic, like the rosters they come from.
"""
import math
from functools import lru_cache

import workforce as wf

LUNCH_HOURS = (11, 12, 13, 14)      # a lunch starts at one of these hours and lasts one hour
MIN_SHIFT_HOURS = 6                 # advisors working fewer hours than this take no lunch
NAIVE_LUNCH = 12


SHRINKAGE = 0.20                    # more people on shift than desks to cover, so that lunches (and breaks) can rotate: the usual call-center "shrinkage"


def present(queue: str) -> list[int]:
    """Advisors on shift each hour: the desks the roster needs plus the shrinkage cover."""
    return [r + math.ceil(r * SHRINKAGE) for r in wf.roster(queue)]


def shifts(queue: str) -> list[list[int]]:
    """The hours each advisor of the queue is on shift (advisor i works when the headcount is above i)."""
    pres = present(queue)
    return [[h for h, p in zip(wf.HOURS, pres) if p > i] for i in range(max(pres))]


def _available(queue: str, lunch: dict[int, int]) -> dict[int, int]:
    """Advisors at their desk each hour once lunches are taken. `lunch` maps advisor index to lunch hour."""
    out = dict(zip(wf.HOURS, present(queue)))
    for h in lunch.values():
        out[h] -= 1
    return out


def _calls(queue: str) -> dict[int, float]:
    return dict(zip(wf.HOURS, (float(x) for x in wf.seasonal(queue))))


def _answered(queue: str, lunch: dict[int, int]) -> float:
    """Calls answered within 20 s over the day."""
    calls, avail, aht = _calls(queue), _available(queue, lunch), wf.QUEUES[queue]["aht"]
    return sum(calls[h] * wf.stats(calls[h], aht, avail[h])["sla"] for h in wf.HOURS)


SHORT_PENALTY = 0.5   # share of an hour's calls charged per advisor missing: an overloaded hour must keep getting worse as more advisors leave it, never become 'free'


def _score(queue: str, lunch: dict[int, int]) -> float:
    """What the search maximizes: calls answered in time, minus a charge for every advisor short of the load, in proportion to that hour's calls (it stops the search from sacrificing a whole hour)."""
    calls, avail, aht = _calls(queue), _available(queue, lunch), wf.QUEUES[queue]["aht"]
    short = sum(calls[h] * max(0.0, calls[h] * aht / 3600 + 1 - avail[h]) for h in wf.HOURS)
    return _answered(queue, lunch) - SHORT_PENALTY * short


def _day_sla(queue: str, lunch: dict[int, int]) -> float:
    calls = _calls(queue)
    return _answered(queue, lunch) / sum(calls.values())


def _worst(queue: str, lunch: dict[int, int]) -> tuple[str, float]:
    """The hour with the lowest service level, and that level."""
    calls, avail, aht = _calls(queue), _available(queue, lunch), wf.QUEUES[queue]["aht"]
    h = min(wf.HOURS, key=lambda x: wf.stats(calls[x], aht, avail[x])["sla"])
    return f"{h}h", round(wf.stats(calls[h], aht, avail[h])["sla"], 2)


def _net_sla(queue: str) -> float:
    """The service level the roster is built for: its desks all covered, nobody away."""
    calls, aht = _calls(queue), wf.QUEUES[queue]["aht"]
    return sum(calls[h] * wf.stats(calls[h], aht, r)["sla"] for h, r in zip(wf.HOURS, wf.roster(queue))) / sum(calls.values())


def plan_queue(queue: str) -> dict:
    eligible = {i: [h for h in LUNCH_HOURS if h in s] for i, s in enumerate(shifts(queue)) if len(s) >= MIN_SHIFT_HOURS}
    eligible = {i: hs for i, hs in eligible.items() if hs}
    naive = {i: (NAIVE_LUNCH if NAIVE_LUNCH in hs else hs[0]) for i, hs in eligible.items()}
    lunch: dict[int, int] = {}
    for i, hs in eligible.items():                       # build the plan one advisor at a time, each at the hour that costs the fewest calls so far...
        lunch[i] = max(hs, key=lambda h: _score(queue, {**lunch, i: h}))
    for _ in range(50):                                  # ...then polish: move one lunch if that wins calls, stop when nothing does                                  # local search: move one lunch if that wins calls, stop when nothing does
        best = None
        base = _score(queue, lunch)
        for i, hs in eligible.items():
            for h in hs:
                if h == lunch[i]:
                    continue
                trial = dict(lunch)
                trial[i] = h
                gain = _score(queue, trial) - base
                if gain > 1e-6 and (best is None or gain > best[0]):
                    best = (gain, i, h)
        if best is None:
            break
        lunch[best[1]] = best[2]
    ros = dict(zip(wf.HOURS, present(queue)))
    count = lambda plan, h: sum(1 for x in plan.values() if x == h)
    return dict(
        queue=queue, name=wf.QUEUES[queue]["name"], advisors=len(shifts(queue)), onLunch=len(eligible),
        lunchHours=[dict(hour=f"{h}h", naive=count(naive, h), planned=count(lunch, h), onDuty=ros[h]) for h in LUNCH_HOURS],
        idealSla=round(_net_sla(queue), 2), baselineSla=round(_day_sla(queue, naive), 2), plannedSla=round(_day_sla(queue, lunch), 2),
        worstBaseline=dict(zip(('hour', 'sla'), _worst(queue, naive))), worstPlanned=dict(zip(('hour', 'sla'), _worst(queue, lunch))),
        _lunch=lunch,
    )


@lru_cache(maxsize=None)
def plan() -> dict:
    queues = [plan_queue(q) for q in wf.QUEUES]
    total = {q: sum(_calls(q).values()) for q in wf.QUEUES}
    weight = sum(total.values())
    overtime = []
    for pq in queues:
        q = pq["queue"]
        calls, avail, aht = _calls(q), _available(q, pq["_lunch"]), wf.QUEUES[q]["aht"]
        for h in wf.HOURS:
            sla = wf.stats(calls[h], aht, avail[h])["sla"]
            need = wf.advisors_needed(calls[h], aht)
            if sla < wf.TARGET_SL and need > avail[h]:
                overtime.append(dict(queue=q, hour=f"{h}h", advisors=need - avail[h], sla=round(sla, 2), calls=round(calls[h]),
                                     text=(f"Queue {q} at {h}h: {need - avail[h]} advisor{'s' if need - avail[h] > 1 else ''} on overtime for that hour "
                                           f"({round(calls[h])} calls expected, {avail[h]} at work after lunches, {need} needed for {wf.TARGET_SL:.0%} within {wf.TARGET_SECONDS} s; now {sla:.0%}).")))
    overtime.sort(key=lambda o: (-o["advisors"], o["sla"]))
    for pq in queues:
        pq.pop("_lunch")
    def avg(key):
        return round(sum(pq[key] * total[pq["queue"]] for pq in queues) / weight, 2)
    return dict(
        idealSla=avg("idealSla"), baselineSla=avg("baselineSla"), plannedSla=avg("plannedSla"), queues=queues,
        overtime=overtime[:6], overtimeHours=sum(o["advisors"] for o in overtime),
        method=(f"With {SHRINKAGE:.0%} more people on shift than desks needed (shrinkage), everyone with a shift of {MIN_SHIFT_HOURS} hours or more takes one hour of lunch starting at {', '.join(f'{h}h' for h in LUNCH_HOURS)}. "
                f"Naive plan: all at {NAIVE_LUNCH}h. Planned: lunches placed one at a time at the hour that loses the fewest calls answered within {wf.TARGET_SECONDS} s "
                "(Erlang C), for a typical day. Overtime is what is still short of the 80 % target after the lunches. Advisors and shifts are synthetic."),
    )
