"""Workforce manager agent: forecast the calls of a queue and simulate what extra advisors would change.

Two real methods, both explainable:
  * Forecast: the average of the same hour over eight past weeks (seasonal profile), corrected during the day by how today is
    running compared with that profile. The history is SYNTHETIC (no real call logs yet): it is drawn from a typical daily shape
    with random call counts, deterministic per queue. Swap load_history() for the real logs and nothing else changes.
  * Staffing: the Erlang C queueing formula. From calls per hour, average handling time and number of advisors it gives the
    chance that a caller waits, the average wait and the share of calls answered within 20 seconds (the service level, SLA).
The reply to a simulation lists the numbers hour by hour so the manager can check every result.
"""
import math
from functools import lru_cache

import numpy as np

HOURS = list(range(9, 18))      # the center is open 9:00 to 18:00
NOW_HOUR = 13                   # the demo day is frozen at 13:00: hours up to 13h have an actual, later hours do not
TARGET_SL = 0.80                # 80 % of calls answered...
TARGET_SECONDS = 20             # ...within 20 seconds
WAIT_CAP = 900                  # an overloaded queue is shown as 15 minutes, not infinity
HISTORY_WEEKS = 8
DAY_FACTORS = [1.10, 1.00, 0.97, 1.00, 0.93]   # Monday to Friday

QUEUES = {   # typical calls per hour at 9h..17h, and average handling time in seconds
    "A": dict(name="Billing", aht=270, shape=[30, 42, 58, 70, 78, 84, 70, 55, 40]),
    "B": dict(name="Plans and billing, premium", aht=300, shape=[20, 28, 40, 52, 60, 72, 60, 45, 35]),
    "C": dict(name="Roaming", aht=360, shape=[10, 14, 18, 22, 24, 26, 22, 18, 14]),
    "D": dict(name="Technical", aht=420, shape=[14, 20, 26, 32, 36, 40, 34, 26, 20]),
    "E": dict(name="Sales", aht=200, shape=[8, 12, 16, 20, 22, 24, 20, 16, 12]),
}
PLAN_ON = 0.85   # rosters are planned on 85 % of the typical demand, so a normal peak runs short: that is what the what-if is for


# ---- Erlang C ---------------------------------------------------------------------------------------
def erlang_c(n: int, a: float) -> float:
    """Chance that a caller has to wait with n advisors and a erlangs of load (calls per second times handling seconds)."""
    if n <= a:
        return 1.0
    b = 1.0
    for k in range(1, n + 1):          # Erlang B by recursion, stable for large n
        b = a * b / (k + a * b)
    return b / (1 - (a / n) * (1 - b))


def stats(calls_per_hour: float, aht: float, n: int) -> dict:
    """Average wait (s), service level (0..1) and advisor occupancy for one hour."""
    a = calls_per_hour * aht / 3600
    if calls_per_hour <= 0:
        return dict(wait=0.0, sla=1.0, occupancy=0.0)
    if n <= a:
        return dict(wait=float(WAIT_CAP), sla=0.0, occupancy=1.0)
    pw = erlang_c(n, a)
    return dict(wait=min(WAIT_CAP, pw * aht / (n - a)), sla=1 - pw * math.exp(-(n - a) * TARGET_SECONDS / aht), occupancy=a / n)


def advisors_needed(calls_per_hour: float, aht: float, target: float = TARGET_SL) -> int:
    n = max(1, math.ceil(calls_per_hour * aht / 3600))
    while stats(calls_per_hour, aht, n)["sla"] < target:
        n += 1
    return n


# ---- forecast ---------------------------------------------------------------------------------------
@lru_cache(maxsize=None)
def load_history(queue: str) -> np.ndarray:
    """(weeks x 5 days x hours) calls per hour. SYNTHETIC: replace with the real call logs."""
    rng = np.random.default_rng(sum(map(ord, queue)) * 7919)
    shape = np.array(QUEUES[queue]["shape"], dtype=float)
    return np.stack([[rng.poisson(shape * f) for f in DAY_FACTORS] for _ in range(HISTORY_WEEKS)])


@lru_cache(maxsize=None)
def today_actuals(queue: str) -> list[int]:
    """Calls that really came in so far today (synthetic: a slightly busier day than usual)."""
    rng = np.random.default_rng(sum(map(ord, queue)) * 104729)
    return [int(x) for x in rng.poisson(np.array(QUEUES[queue]["shape"]) * 1.06)[: NOW_HOUR - HOURS[0] + 1]]


def seasonal(queue: str) -> np.ndarray:
    """Typical calls per hour on a Wednesday: the same weekday over the past weeks, hour by hour."""
    return load_history(queue)[:, 2, :].mean(axis=0)


def forecast(queue: str) -> list[dict]:
    base, actual = seasonal(queue), today_actuals(queue)
    k = len(actual)
    # how is today running against its profile? Half of the gap is carried into the hours to come
    ratio = float(np.clip(sum(actual) / max(1.0, base[:k].sum()), 0.8, 1.25))
    adjust = 1 + (ratio - 1) / 2
    out = []
    for i, h in enumerate(HOURS):
        past = i < k
        out.append(dict(hour=f"{h}h", actual=actual[i] if past else None, forecast=round(float(base[i] if past else base[i] * adjust))))
    return out


@lru_cache(maxsize=None)
def roster(queue: str) -> list[int]:
    """Advisors on duty each hour: what 85 % of the typical demand needs for 80 % of calls answered in 20 s."""
    q = QUEUES[queue]
    return [advisors_needed(float(c) * PLAN_ON, q["aht"]) for c in seasonal(queue)]


# ---- what-if ----------------------------------------------------------------------------------------
def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _overlap(h: int, start: int, end: int) -> float:
    """Share of the hour h:00 to h+1:00 that lies inside the window."""
    return max(0, min(end, (h + 1) * 60) - max(start, h * 60)) / 60


def simulate(queue: str, extra: int, start: str, end: str) -> dict:
    q, s, e = QUEUES[queue], _minutes(start), _minutes(end)
    fc, ros = {int(f["hour"][:-1]): f["forecast"] for f in forecast(queue)}, dict(zip(HOURS, roster(queue)))
    rows, base_w, sim_w, base_s, sim_s, weight = [], 0.0, 0.0, 0.0, 0.0, 0.0
    for h in HOURS:
        share = _overlap(h, s, e)
        if share <= 0:
            continue
        calls = fc[h]
        n0, n1 = ros[h], max(0, ros[h] + extra)
        b, a = stats(calls, q["aht"], n0), stats(calls, q["aht"], n1)
        w = calls * share
        weight += w
        base_w += b["wait"] * w; sim_w += a["wait"] * w; base_s += b["sla"] * w; sim_s += a["sla"] * w
        rows.append(dict(hour=f"{h}h", calls=calls, advisors=n0, simulatedAdvisors=n1, baselineWaitSec=round(b["wait"]), simulatedWaitSec=round(a["wait"]),
                         baselineSla=round(b["sla"], 2), simulatedSla=round(a["sla"], 2), needed=advisors_needed(calls, q["aht"])))
    if weight == 0:
        return dict(baselineWaitSec=0, simulatedWaitSec=0, baselineSla=1.0, simulatedSla=1.0, hours=[], method=METHOD,
                    recommendations=["No opening hours in this window: the center is open from 9:00 to 18:00."])
    return dict(
        baselineWaitSec=round(base_w / weight), simulatedWaitSec=round(sim_w / weight),
        baselineSla=round(base_s / weight, 2), simulatedSla=round(sim_s / weight, 2),
        recommendations=recommend(queue, rows, extra), hours=rows, method=METHOD,
    )


METHOD = (f"Erlang C queueing model: {TARGET_SL:.0%} of calls answered within {TARGET_SECONDS} s is the target. "
          "Calls come from a seasonal forecast of synthetic history; rosters are planned on 85 % of typical demand.")


def recommend(queue: str, rows: list[dict], extra: int) -> list[str]:
    """Ranked, each one backed by the hour-by-hour numbers: biggest service-level gap first."""
    out: list[str] = []
    short = sorted((r for r in rows if r["baselineSla"] < TARGET_SL), key=lambda r: r["baselineSla"])
    for r in short[:3]:
        gap = r["needed"] - r["advisors"]
        if gap > 0:
            out.append(f"Add {gap} advisor{'s' if gap > 1 else ''} on queue {queue} at {r['hour']}: {r['calls']} calls expected, "
                       f"{r['needed']} advisors are needed to answer {TARGET_SL:.0%} within {TARGET_SECONDS} s (now {r['baselineSla']:.0%}).")
    donors = []   # other queues that have more advisors than the target needs, at the hours that are short here
    for other in QUEUES:
        if other == queue:
            continue
        ofc = {int(f["hour"][:-1]): f["forecast"] for f in forecast(other)}
        for r in short:
            h = int(r["hour"][:-1])
            spare = roster(other)[HOURS.index(h)] - advisors_needed(ofc[h], QUEUES[other]["aht"])
            if spare >= 1:
                donors.append((spare, other, r["hour"]))
    for spare, other, hour in sorted(donors, reverse=True)[:2]:
        out.append(f"Move 1 advisor from queue {other} to {queue} at {hour}: queue {other} has {spare} more than it needs for its own target.")
    if any(r["baselineWaitSec"] > 180 for r in rows):
        out.append("Offer a callback when the wait passes 3 minutes: the average wait is above 3 minutes in this window.")
    if extra < 0 and rows and all(r["baselineSla"] >= TARGET_SL for r in rows):
        out.append("Removing advisors lowers the service level here: keep the roster unless the hours are needed elsewhere.")
    if not out:
        out.append(f"The roster already meets {TARGET_SL:.0%} within {TARGET_SECONDS} s in this window: no change needed.")
    return out
