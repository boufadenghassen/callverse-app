"""Workforce dataset ingestion and mixed real/synthetic seeding.

The public CC0 source is a daily aggregate without timestamps or queue labels.
Daily values are kept unchanged as ``real_daily``.  A 15-minute training view
is derived only for simulator bootstrapping and is labelled
``real_daily_disaggregated`` so it cannot be mistaken for observed intervals.
"""
from __future__ import annotations

import csv
import json
import os
import random
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Iterable

SOURCE_URL = "https://www.kaggle.com/datasets/satvicoder/call-center-data"
SOURCE_LICENSE = "CC0 Public Domain"
DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "datasets" / "workforce-real" / "Call Center Data.csv"
OUTPUT_NAME = "mixed-workforce-15m.jsonl"

# A 36-slot 15-minute profile covering a 9-hour operating day.
_PROFILE = (
    0.010, 0.012, 0.015, 0.018, 0.020, 0.022, 0.025, 0.028, 0.030,
    0.032, 0.034, 0.036, 0.038, 0.040, 0.042, 0.044, 0.046, 0.048,
    0.050, 0.052, 0.054, 0.055, 0.054, 0.052, 0.050, 0.048, 0.046,
    0.044, 0.042, 0.038, 0.034, 0.030, 0.026, 0.022, 0.017, 0.011,
)
_PROFILE = tuple(value / sum(_PROFILE) for value in _PROFILE)
_QUEUES = ("A", "B", "C", "D", "E")
DEFAULT_SEED = DEFAULT_SOURCE.parent / OUTPUT_NAME


def _duration(value: str) -> float:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _percent(value: str) -> float:
    return float(value.rstrip("%")) / 100


def load_real_daily(path: Path | None = None) -> list[dict]:
    """Load and validate the untouched daily aggregates from the CC0 source."""
    path = path or DEFAULT_SOURCE
    if not path.exists():
        raise FileNotFoundError(f"Workforce source data not found: {path}")
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            incoming = int(row["Incoming Calls"])
            answered = int(row["Answered Calls"])
            abandoned = int(row["Abandoned Calls"])
            if incoming < 0 or answered < 0 or abandoned < 0 or answered + abandoned > incoming:
                raise ValueError(f"Invalid call totals in source row {row.get('Index')}")
            rows.append({
                "source": "real_daily",
                "sourceUrl": SOURCE_URL,
                "license": SOURCE_LICENSE,
                "day": int(row["Index"]),
                "incoming": incoming,
                "answered": answered,
                "abandoned": abandoned,
                "answerRate": _percent(row["Answer Rate"]),
                "answerSpeedSec": _duration(row["Answer Speed (AVG)"]),
                "ahtSec": _duration(row["Talk Duration (AVG)"]),
                "waitingSec": _duration(row["Waiting Time (AVG)"]),
                "serviceLevel": _percent(row["Service Level (20 Seconds)"]),
            })
    if not rows:
        raise ValueError(f"Workforce source data is empty: {path}")
    return rows


def _disaggregate(day: dict) -> Iterable[dict]:
    """Create labelled 15-minute bootstrap rows from a daily aggregate.

    This is not a measurement of the original intervals.  It distributes the
    daily total across the demo's 9-hour profile and queue mix so the simulator
    can learn realistic scale while preserving provenance.
    """
    for interval, weight in enumerate(_PROFILE):
        calls = round(day["incoming"] * weight)
        for queue_index, queue in enumerate(_QUEUES):
            queue_share = (0.28, 0.24, 0.12, 0.22, 0.14)[queue_index]
            queue_calls = round(calls * queue_share)
            yield {
                "source": "real_daily_disaggregated",
                "sourceDay": day["day"],
                "interval": interval,
                "queue": queue,
                "calls": queue_calls,
                "ahtSec": day["ahtSec"],
                "abandoned": round(day["abandoned"] * queue_share * weight),
                "serviceLevel": day["serviceLevel"],
                "provenance": "daily aggregate disaggregated with synthetic intraday and queue profiles",
            }


def _synthetic(seed: int, days: int) -> Iterable[dict]:
    """Generate simulator rows with an explicit synthetic provenance label."""
    rng = random.Random(seed)
    for day in range(days):
        for interval, weight in enumerate(_PROFILE):
            for queue_index, queue in enumerate(_QUEUES):
                base = (30, 25, 12, 22, 14)[queue_index] * (1 + 3 * weight)
                calls = max(0, round(rng.gauss(base, max(1.0, base * 0.12))))
                yield {
                    "source": "synthetic",
                    "sourceDay": day,
                    "interval": interval,
                    "queue": queue,
                    "calls": calls,
                    "ahtSec": (270, 300, 360, 420, 200)[queue_index],
                    "abandoned": 0,
                    "serviceLevel": None,
                    "provenance": "seeded simulator episode",
                }


def mixed_rows(
    real_path: Path = DEFAULT_SOURCE,
    synthetic_days: int = 8,
    seed: int = 42,
) -> list[dict]:
    """Return real-derived bootstrap rows followed by independent synthetic rows."""
    real = load_real_daily(real_path)
    rows = list(item for day in real for item in _disaggregate(day))
    rows.extend(_synthetic(seed, synthetic_days))
    return rows


def load_seed_rows(path: Path | None = None) -> list[dict]:
    """Load the generated mixed seed, failing clearly on malformed rows."""
    seed_path = path or Path(os.environ.get("WORKFORCE_DATA_PATH", DEFAULT_SEED))
    if not seed_path.exists():
        return mixed_rows()
    rows = []
    with seed_path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid workforce seed JSON at line {line_number}") from error
            if row.get("interval") not in range(36) or row.get("source") not in {
                "real_daily_disaggregated", "synthetic"
            }:
                raise ValueError(f"Invalid workforce seed row at line {line_number}")
            rows.append(row)
    if not rows:
        raise ValueError(f"Workforce seed is empty: {seed_path}")
    return rows


@lru_cache(maxsize=8)
def real_calls_by_hour(path: Path | None = None) -> dict[int, dict[str, int]]:
    """Aggregate real-derived rows into average queue calls per operating hour."""
    # The generated JSONL is useful for training provenance, but the compact
    # daily source is enough to reconstruct the same deterministic aggregates.
    # Avoid parsing hundreds of thousands of JSON lines on every service start.
    if path is None and not os.environ.get("WORKFORCE_DATA_PATH"):
        daily = load_real_daily()
        queue_shares = (0.28, 0.24, 0.12, 0.22, 0.14)
        calls_by_hour: dict[int, dict[str, int]] = {}
        for hour in range(9, 18):
            profile_share = sum(_PROFILE[(hour - 9) * 4:(hour - 8) * 4])
            calls_by_hour[hour] = {
                queue: max(0, round(
                    sum(day["incoming"] for day in daily) / len(daily)
                    * profile_share * queue_shares[index]
                ))
                for index, queue in enumerate(_QUEUES)
            }
        return calls_by_hour
    grouped: dict[tuple[int, str, int], int] = defaultdict(int)
    for row in load_seed_rows(path):
        if row["source"] != "real_daily_disaggregated":
            continue
        hour = 9 + row["interval"] // 4
        grouped[(hour, row["queue"], row["sourceDay"])] += int(row["calls"])
    days = {day for hour, queue, day in grouped}
    if not days:
        return {}
    return {
        hour: {
            queue: max(0, round(sum(grouped[(hour, queue, day)] for day in days) / len(days)))
            for queue in _QUEUES
        }
        for hour in range(9, 18)
    }


@lru_cache(maxsize=8)
def real_forecast_and_actual(path: Path | None = None) -> tuple[dict[int, dict[str, int]], dict[int, dict[str, int]]]:
    """Return a real-data holdout forecast and latest-day actuals by hour.

    The source is daily, so both series use the documented intraday profile.
    Earlier days form the forecast baseline and the latest day is the holdout
    actual; neither is presented as native 15-minute instrumentation.
    """
    daily = load_real_daily(path)
    if len(daily) < 2:
        average = real_calls_by_hour(path)
        return average, average
    queue_shares = (0.28, 0.24, 0.12, 0.22, 0.14)

    def day_by_hour(day: dict) -> dict[int, dict[str, int]]:
        return {
            hour: {
                queue: max(0, round(
                    day["incoming"]
                    * sum(_PROFILE[(hour - 9) * 4:(hour - 8) * 4])
                    * queue_shares[index]
                ))
                for index, queue in enumerate(_QUEUES)
            }
            for hour in range(9, 18)
        }

    # The source contains occasional partial days; keep the latest complete
    # enough record as holdout so the comparison is not flattened at zero.
    holdout_day = next((day for day in reversed(daily) if day["incoming"] >= 50), daily[-1])
    history_days = [day for day in daily if day is not holdout_day]
    holdout = day_by_hour(holdout_day)
    history = [day_by_hour(day) for day in history_days]
    forecast = {
        hour: {
            queue: round(sum(day[hour][queue] for day in history) / len(history))
            for queue in _QUEUES
        }
        for hour in range(9, 18)
    }
    return forecast, holdout


def seed_summary(path: Path | None = None) -> dict:
    rows = load_seed_rows(path)
    by_source: dict[str, int] = defaultdict(int)
    for row in rows:
        by_source[row["source"]] += 1
    return {
        "rows": len(rows),
        "bySource": dict(by_source),
        "intervalMinutes": 15,
        "sourceUrl": SOURCE_URL,
        "license": SOURCE_LICENSE,
    }


def real_scenarios(path: Path | None = None) -> list[dict]:
    """Build reproducible stress scenarios from the ingested real-derived demand.

    The source is daily aggregate data disaggregated to 15-minute bootstrap
    rows, so these are evaluation scenarios, not claims about observed events.
    """
    base = real_calls_by_hour(path)
    if not base:
        raise ValueError("No real-derived workforce rows are available for scenarios.")

    def transform(name: str, description: str, fn) -> dict:
        return {
            "name": name,
            "description": description,
            "source": "real_daily_disaggregated",
            "calls": {
                hour: {queue: max(0, round(fn(hour, queue, calls[queue]))) for queue in _QUEUES}
                for hour, calls in base.items()
            },
        }

    return [
        {
            "name": "real-baseline",
            "description": "Average demand reconstructed from the CC0 daily aggregates.",
            "source": "real_daily_disaggregated",
            "calls": base,
        },
        transform("peak-load", "25% demand increase across all real-derived queues.", lambda _h, _q, value: value * 1.25),
        transform("low-volume", "25% demand decrease across all real-derived queues.", lambda _h, _q, value: value * 0.75),
        transform("premium-spike", "50% increase in premium queue B during the afternoon.", lambda hour, queue, value: value * (1.5 if queue == "B" and hour >= 14 else 1)),
        transform("technical-incident", "100% increase in technical queue D during the afternoon.", lambda hour, queue, value: value * (2 if queue == "D" and hour >= 14 else 1)),
        transform("queue-imbalance", "Billing demand rises while sales demand falls.", lambda _h, queue, value: value * (1.4 if queue == "A" else 0.6 if queue == "E" else 1)),
    ]


def write_mixed_dataset(
    output: Path | None = None,
    real_path: Path = DEFAULT_SOURCE,
    synthetic_days: int = 8,
    seed: int = 42,
) -> Path:
    """Write a reproducible JSONL seed file outside git's tracked source tree."""
    destination = output or real_path.parent / OUTPUT_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as target:
        for row in mixed_rows(real_path, synthetic_days, seed):
            target.write(json.dumps(row, separators=(",", ":")) + "\n")
    return destination


if __name__ == "__main__":
    print(write_mixed_dataset())
